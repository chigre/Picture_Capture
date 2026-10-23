"""Complete Tk batch-task lifecycle, foreground ownership and parallel dispatch.

Owns 12 related PictureCaptureApp methods: foreground page ownership
and keypress safety, sequential and parallel batch dispatch including
GPU preflight, queue polling, progress and completion transitions,
pause/stop requests and delayed batch UI teardown.

Original app methods remain public/bindable with unchanged call shapes
and use per-invocation original global bindings. Do not import heavy
PictureCaptureApp in this module or change queue/status/output formats.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tkinter as tk


@dataclass(frozen=True)
class BatchWorkflowDeps:
    """Original module globals captured live to retain patch/test semantics."""
    FIRST_COMPLETED: object
    ProcessPoolExecutor: object
    wait: object
    os: object
    queue: object
    threading: object
    multiprocessing: object
    traceback: object
    tk: object
    messagebox: object
    resolve_crop_worker_count: object


def _foreground_batch_state(
    deps: BatchWorkflowDeps, self, index: int | None = None) -> str:
    if index is None:
        index = self.current_index
    if not self._batch_active or not self._batch_foreground_pages:
        return ""
    with self._batch_state_lock:
        return self._batch_page_states.get(int(index), "")


def _set_foreground_batch_state(
    deps: BatchWorkflowDeps, self, index: int, state: str) -> None:
    with self._batch_state_lock:
        if index in self._batch_page_states:
            self._batch_page_states[index] = state


def _claim_page_for_manual_edit(
    deps: BatchWorkflowDeps, self, index: int | None = None) -> bool:
    """ claim page for manual edit."""
    if index is None:
        index = self.current_index
    if not self._batch_active:
        return True
    if not self._batch_foreground_pages:
        if getattr(self, "_batch_allow_pdic_edits", False) and not self.polygon_draw_var.get():
            return True
        self.status_var.set("批量任务正在运行；该任务不支持同时编辑页面。")
        return False
    with self._batch_state_lock:
        state = self._batch_page_states.get(int(index), "")
        if state == "processing":
            self.status_var.set("当前页正在后台处理，暂时只读；完成后即可校对。")
            return False
        if state == "pending":
            self._batch_page_states[int(index)] = "manual_locked"
            state = "manual_locked"
    if state == "manual_locked":
        self._update_page_row(int(index))
        self.status_var.set("当前页已人工锁定：本轮后台批处理将跳过此页，可安全校对。")
    return True


def _can_save_current_during_batch_navigation(
    deps: BatchWorkflowDeps, self) -> bool:
    if not self._batch_active:
        return True
    if not self._batch_foreground_pages:
        return bool(self._batch_allow_pdic_edits)
    state = self._foreground_batch_state(self.current_index)
    # Never overwrite worker-owned or pending pages with stale foreground data.
    return state not in {"pending", "processing"}


def _entry_keypress_batch_guard(
    deps: BatchWorkflowDeps, self, event: tk.Event) -> str | None:
    """Claim a pending page before a key can mutate a foreground Entry."""
    if not self._batch_active:
        return None
    keysym = str(getattr(event, "keysym", ""))
    # Cursor/navigation/focus keys do not constitute a manual edit.
    non_edit = {"Left", "Right", "Up", "Down", "Home", "End", "Tab", "ISO_Left_Tab",
                "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
                "Escape", "Return"}
    if keysym in non_edit:
        return None
    if not self._claim_page_for_manual_edit():
        return "break"
    return None


def _start_batch_task(
    deps: BatchWorkflowDeps, 
    self, title: str, items, worker, on_done=None, item_label=None,
    *, foreground_page_edit: bool = False, page_indexer=None,
    refresh_page_quality: bool = True,
    allow_page_navigation: bool = True,
    allow_pdic_edits: bool = False,
    flush_deferred_save: bool = True,
) -> bool:
    """ start batch task."""
    wait = deps.wait
    queue = deps.queue
    threading = deps.threading
    traceback = deps.traceback
    messagebox = deps.messagebox
    if self._batch_active:
        messagebox.showinfo("批量任务正在运行", "已有批量任务正在运行，请先暂停或停止。", parent=self)
        return False
    if self._ui_worker_key_active("crop-width-normalization"):
        self.status_var.set("PNG 宽度标准化仍在运行；请先完成或停止。")
        return False
    if self._ui_worker_key_active("project-load"):
        self.status_var.set("项目仍在后台打开；完成后再启动批量任务。")
        return False
    if self._ui_worker_key_active("profile-validation"):
        self.status_var.set("Project Profile 测试仍在运行或安全结束中；完成后再启动批量任务。")
        return False
    if self._ui_worker_key_active("headword-order-finalize"):
        self.status_var.set("全项目词头顺序报告仍在汇总；完成后再启动新的批量任务。")
        return False
    if self._ui_close_requested:
        return False
    if flush_deferred_save:
        self._flush_deferred_page_save()
    items = list(items)
    if not items:
        self.status_var.set("没有需要处理的页面")
        return False

    self._batch_active = True
    self._batch_refresh_page_quality = bool(refresh_page_quality)
    self._batch_foreground_pages = bool(foreground_page_edit)
    self._batch_allow_page_navigation = bool(allow_page_navigation)
    self._batch_allow_pdic_edits = bool(allow_pdic_edits)
    self._batch_skipped_count = 0
    indexer = page_indexer or (lambda item: int(item))
    with self._batch_state_lock:
        self._batch_page_states = {indexer(item): "pending" for item in items} if foreground_page_edit else {}
    self._batch_title = title
    self._batch_on_done = on_done
    self._batch_stop_event.clear()
    self._batch_pause_event.set()
    self._batch_in_item = False
    self.batch_progress_var.set(0.0)
    self.batch_progress.configure(maximum=100.0)
    self.batch_text_var.set(f"{title}：准备开始 0/{len(items)}")
    self.batch_pause_button.configure(text="暂停", state="normal")
    self.batch_stop_button.configure(text="停止", state="normal")
    if not self.batch_bar.winfo_manager():
        self.batch_bar.pack(side="right", fill="x")
    self.status_var.set(
        f"{title}开始：共 {len(items)} 页。" +
        ("可切换并校对其他页面；人工修改的待处理页会自动锁定并由后台跳过。" if foreground_page_edit
         else ("可翻页编辑 PDIC；PPP 只读。" if allow_pdic_edits
               else "可翻页查看；编辑保护开启，暂停/停止在当前页完成后生效。"))
    )
    if foreground_page_edit:
        for item in items:
            try:
                self._update_page_row(indexer(item))
            except Exception:
                pass

    try:
        while True:
            self._batch_queue.get_nowait()
    except queue.Empty:
        pass

    total = len(items)
    labeler = item_label or (lambda item: str(item))

    def runner() -> None:
        results = []
        completed = 0
        try:
            for position, item in enumerate(items, 1):
                while not self._batch_pause_event.wait(0.10):
                    if self._batch_stop_event.is_set():
                        break
                if self._batch_stop_event.is_set():
                    break
                label = labeler(item)
                item_index = indexer(item) if foreground_page_edit else None
                if foreground_page_edit:
                    with self._batch_state_lock:
                        state = self._batch_page_states.get(item_index, "pending")
                        if state == "manual_locked":
                            self._batch_skipped_count += 1
                            completed += 1
                            self._batch_queue.put(("skipped", completed, total, label, item_index))
                            continue
                        self._batch_page_states[item_index] = "processing"
                self._batch_queue.put(("item", position, total, label, item_index))
                result = worker(item, position, total)
                results.append(result)
                completed += 1
                if foreground_page_edit:
                    with self._batch_state_lock:
                        if self._batch_page_states.get(item_index) == "processing":
                            self._batch_page_states[item_index] = "done"
                self._batch_queue.put(("progress", completed, total, label, result, item_index))
                if self._batch_stop_event.is_set():
                    break
            self._batch_queue.put(("done", completed, total, self._batch_stop_event.is_set(), results))
        except Exception as exc:
            self._batch_queue.put(("error", completed, total, exc, traceback.format_exc(), results))

    self._batch_thread = threading.Thread(target=runner, name=f"PictureCapture-{title}", daemon=True)
    self._batch_thread.start()
    self._batch_poll_job = self.after(80, self._poll_batch_queue)
    return True


def _start_parallel_batch_task(
    deps: BatchWorkflowDeps, 
    self, title: str, items, worker_func, job_builder, result_consumer=None,
    on_done=None, item_label=None, max_workers: int = 0,
    *, allow_page_navigation: bool = True, allow_pdic_edits: bool = False,
    foreground_page_edit: bool = False, page_indexer=None,
    gpu_preflight_func=None, gpu_job_builder=None,
    respect_cpu_workers: bool = False, isolate_worker: bool = False,
) -> bool:
    """Run bounded page jobs; optional one-process GPU preflight before CPU."""
    FIRST_COMPLETED = deps.FIRST_COMPLETED
    ProcessPoolExecutor = deps.ProcessPoolExecutor
    wait = deps.wait
    os = deps.os
    queue = deps.queue
    threading = deps.threading
    multiprocessing = deps.multiprocessing
    traceback = deps.traceback
    messagebox = deps.messagebox
    resolve_crop_worker_count = deps.resolve_crop_worker_count
    if self._batch_active:
        messagebox.showinfo("批量任务正在运行", "已有批量任务正在运行，请先暂停或停止。", parent=self)
        return False
    if self._ui_worker_key_active("crop-width-normalization"):
        self.status_var.set("PNG 宽度标准化仍在运行；请先完成或停止。")
        return False
    if self._ui_worker_key_active("project-load"):
        self.status_var.set("项目仍在后台打开；完成后再启动批量任务。")
        return False
    if self._ui_worker_key_active("profile-validation"):
        self.status_var.set("Project Profile 测试仍在运行或安全结束中；完成后再启动批量任务。")
        return False
    if self._ui_worker_key_active("headword-order-finalize"):
        self.status_var.set("全项目词头顺序报告仍在汇总；完成后再启动新的批量任务。")
        return False
    if self._ui_close_requested:
        return False
    self._flush_deferred_page_save()
    items = list(items)
    if not items:
        self.status_var.set("没有需要处理的页面")
        return False

    workers = (
        max(1, min(int(max_workers), len(items), os.cpu_count() or 1))
        if respect_cpu_workers and int(max_workers) > 0
        else resolve_crop_worker_count(max_workers)
    )
    # Light single-worker jobs use the sequential runner.
    if workers <= 1 and gpu_preflight_func is None and not isolate_worker:
        def serial_worker(item, position, total):
            args = job_builder(item, position, total)
            raw = worker_func(*args)
            return result_consumer(item, raw) if result_consumer is not None else raw
        return self._start_batch_task(
            title, items, serial_worker, on_done, item_label,
            allow_page_navigation=allow_page_navigation,
            allow_pdic_edits=allow_pdic_edits,
            foreground_page_edit=foreground_page_edit,
            page_indexer=page_indexer,
        )

    self._batch_active = True
    self._batch_parallel = True
    self._batch_allow_page_navigation = bool(allow_page_navigation)
    self._batch_allow_pdic_edits = bool(allow_pdic_edits)
    self._batch_foreground_pages = bool(foreground_page_edit)
    self._batch_skipped_count = 0
    page_id = page_indexer or (lambda item: int(item))
    with self._batch_state_lock:
        self._batch_page_states = (
            {page_id(item): "pending" for item in items}
            if foreground_page_edit else {}
        )
    self._batch_title = title
    self._batch_on_done = on_done
    self._batch_stop_event.clear()
    self._batch_pause_event.set()
    self._batch_in_item = False
    self.batch_progress_var.set(0.0)
    self.batch_progress.configure(maximum=100.0)
    self.batch_text_var.set(f"{title}：准备并行处理 0/{len(items)}（{workers}进程）")
    self.batch_pause_button.configure(text="暂停", state="normal")
    self.batch_stop_button.configure(text="停止", state="normal")
    if not self.batch_bar.winfo_manager():
        self.batch_bar.pack(side="top", fill="x")
    self.status_var.set(
        (f"{title}开始：一个 GPU 预检进程 + {workers} 个 CPU 处理进程；"
         if gpu_preflight_func is not None else
         f"{title}开始：共 {len(items)} 页，CPU并行 {workers} 进程。")
        + "暂停/停止不会再派发新页面。"
        + (" 可校对其他待处理页；手工锁定页面将安全跳过。" if foreground_page_edit
           else " 可翻页编辑 PDIC；PPP 只读。" if allow_pdic_edits else "")
    )

    if foreground_page_edit:
        for item in items:
            try:
                self._update_page_row(page_id(item))
            except Exception:
                pass

    try:
        while True:
            self._batch_queue.get_nowait()
    except queue.Empty:
        pass

    total = len(items)
    labeler = item_label or (lambda item: str(item))

    def runner() -> None:
        results = []
        completed = 0
        next_index = 0
        futures = {}
        context = multiprocessing.get_context("spawn")
        executor = ProcessPoolExecutor(max_workers=workers, mp_context=context)
        gpu_executor = (
            ProcessPoolExecutor(max_workers=1, mp_context=context)
            if gpu_preflight_func is not None else None
        )
        try:
            while True:
                # Bound submissions so pause/stop halts new dispatches.
                while (
                    self._batch_pause_event.is_set()
                    and not self._batch_stop_event.is_set()
                    and next_index < total
                    and len(futures) < workers
                ):
                    item = items[next_index]
                    position = next_index + 1
                    label = labeler(item)
                    item_index = page_id(item) if foreground_page_edit else None
                    next_index += 1
                    if foreground_page_edit:
                        # Lock protects pending/manual ownership.
                        with self._batch_state_lock:
                            state = self._batch_page_states.get(item_index, "pending")
                            if state == "manual_locked":
                                self._batch_skipped_count += 1
                                completed += 1
                                self._batch_queue.put((
                                    "skipped", completed, total, label, item_index
                                ))
                                continue
                            self._batch_page_states[item_index] = "processing"
                        self._batch_queue.put((
                            "item", position, total, label, item_index
                        ))
                    args = job_builder(item, position, total)
                    if gpu_executor is not None:
                        if gpu_job_builder is None:
                            raise RuntimeError("Missing GPU preflight job builder")
                        # GPU preflight is a single long-lived process.
                        gpu_args = gpu_job_builder(item, position, total)
                        self._batch_queue.put((
                            "pipeline_stage", position, total, label, "GPU版面预检",
                        ))
                        prepared = gpu_executor.submit(
                            gpu_preflight_func, *gpu_args
                        ).result()
                        self._batch_queue.put((
                            "pipeline_stage", position, total, label, "CPU画线与保存",
                        ))
                        args = (*args, prepared)
                    future = executor.submit(worker_func, *args)
                    futures[future] = (item, position, label, item_index)
                    self._batch_queue.put((
                        "parallel_state", completed, total, len(futures), label, workers
                    ))

                if not futures:
                    if self._batch_stop_event.is_set() or next_index >= total:
                        break
                    # Paused before all pages have been dispatched.
                    self._batch_pause_event.wait(0.10)
                    continue

                done_set, _ = wait(tuple(futures), timeout=0.10, return_when=FIRST_COMPLETED)
                if not done_set:
                    continue
                for future in done_set:
                    item, _position, label, item_index = futures.pop(future)
                    raw = future.result()
                    result = result_consumer(item, raw) if result_consumer is not None else raw
                    results.append(result)
                    completed += 1
                    if foreground_page_edit:
                        with self._batch_state_lock:
                            if self._batch_page_states.get(item_index) == "processing":
                                self._batch_page_states[item_index] = "done"
                    self._batch_queue.put((
                        "parallel_progress", completed, total, label, result,
                        len(futures), workers, item_index
                    ))

            self._batch_queue.put((
                "done", completed, total, self._batch_stop_event.is_set(), results
            ))
        except Exception as exc:
            self._batch_stop_event.set()
            self._batch_queue.put((
                "error", completed, total, exc, traceback.format_exc(), results
            ))
        finally:
            executor.shutdown(wait=True, cancel_futures=True)
            if gpu_executor is not None:
                gpu_executor.shutdown(wait=True, cancel_futures=True)

    self._batch_thread = threading.Thread(
        target=runner, name=f"PictureCapture-{title}-parallel", daemon=True
    )
    self._batch_thread.start()
    self._batch_poll_job = self.after(80, self._poll_batch_queue)
    return True


def _poll_batch_queue(
    deps: BatchWorkflowDeps, self) -> None:
    queue = deps.queue
    self._batch_poll_job = None
    finished = False
    from .batch_progress_budget import (
        SATURATED_BATCH_POLL_DELAY_MS, batch_poll_should_yield,
        start_batch_poll_budget,
    )
    processed_events = 0
    poll_started = start_batch_poll_budget()
    yielded = False
    while True:
        try:
            event = self._batch_queue.get_nowait()
        except queue.Empty:
            break
        processed_events += 1
        kind = event[0]
        if kind == "item":
            _kind, position, total, label, item_index = event
            self._batch_in_item = True
            if item_index is not None:
                self._update_page_row(int(item_index))
                if int(item_index) == self.current_index:
                    self.redraw()
            self.batch_text_var.set(f"{self._batch_title} {position}/{total}：{label}")
            if self._batch_foreground_pages:
                self.status_var.set(f"{self._batch_title} {position}/{total}：{label}（可同时校对其他页面）")
            else:
                self.status_var.set(f"{self._batch_title} {position}/{total}：{label}（可暂停或停止）")
        elif kind == "skipped":
            _kind, completed, total, label, item_index = event
            self.batch_progress_var.set(100.0 * completed / max(1, total))
            self._update_page_row(int(item_index))
            self.batch_text_var.set(f"{self._batch_title}：{completed}/{total}，人工锁定跳过 {label}")
            self.status_var.set(f"后台已跳过人工锁定页 {label}；你的校对内容不会被覆盖。")
        elif kind == "progress":
            _kind, completed, total, label, _result, item_index = event
            self._batch_in_item = False
            self.batch_progress_var.set(100.0 * completed / max(1, total))
            if item_index is not None:
                self._update_page_row(int(item_index))
                if int(item_index) == self.current_index and self._foreground_batch_state(int(item_index)) == "done":
                    # Reload without stale save.
                    self.load_page(int(item_index))
            if not self._batch_pause_event.is_set() and not self._batch_stop_event.is_set():
                self.batch_text_var.set(f"{self._batch_title}：已暂停 {completed}/{total}")
                self.status_var.set(f"{self._batch_title}已暂停：完成 {completed}/{total} 页；点击“继续”恢复。")
            elif self._batch_stop_event.is_set():
                self.batch_text_var.set(f"{self._batch_title}：正在安全停止 {completed}/{total}")
            else:
                self.batch_text_var.set(f"{self._batch_title}：已完成 {completed}/{total}：{label}")
                self.status_var.set(f"{self._batch_title}：已完成 {completed}/{total} 页，最近完成 {label}")
        elif kind == "pipeline_stage":
            _kind, position, total, label, stage = event
            self.batch_text_var.set(
                f"{self._batch_title} {position}/{total}：{stage} · {label}"
            )
            self.status_var.set(
                f"{self._batch_title}：{stage}（{label}）；"
                "GPU模型只在一个进程中运行。"
            )
        elif kind == "parallel_state":
            _kind, completed, total, active, label, workers = event
            self._batch_in_item = active > 0
            self.batch_text_var.set(
                f"{self._batch_title}：{completed}/{total}，"
                + f"并行 {active}/{workers} 页"
            )
            self.status_var.set(
                f"{self._batch_title}并行处理中：完成 {completed}/{total}，当前 {active} 页运行；最近派发 {label}"
            )
        elif kind == "parallel_progress":
            _kind, completed, total, label, _result, active, workers, *page_ids = event
            self._batch_in_item = active > 0
            self.batch_progress_var.set(100.0 * completed / max(1, total))
            if page_ids and page_ids[0] is not None:
                item_index = int(page_ids[0])
                self._update_page_row(item_index)
                if (item_index == self.current_index
                        and self._foreground_batch_state(item_index) == "done"):
                    # Reload saved PDIC after worker commit.
                    self.load_page(item_index)
            if not self._batch_pause_event.is_set() and not self._batch_stop_event.is_set():
                if active:
                    self.batch_text_var.set(
                        f"{self._batch_title}：暂停中 {completed}/{total}（等待 {active} 页完成）"
                    )
                    self.status_var.set("暂停请求已生效：不再派发新页面；已启动页面完成后完全暂停。")
                else:
                    self.batch_text_var.set(f"{self._batch_title}：已暂停 {completed}/{total}")
                    self.status_var.set(f"{self._batch_title}已暂停：完成 {completed}/{total} 页；点击“继续”恢复。")
            elif self._batch_stop_event.is_set():
                self.batch_text_var.set(
                    f"{self._batch_title}：正在安全停止 {completed}/{total}（剩余运行 {active} 页）"
                )
            else:
                self.batch_text_var.set(
                    f"{self._batch_title}：已完成 {completed}/{total}（并行 {active}/{workers} 页）"
                )
            if self._batch_title == "精修画线" and isinstance(_result, dict):
                from ..refinement.progress import report_refinement_page
                report_refinement_page(self, completed, total, label, _result)
        elif kind == "done":
            _kind, completed, total, stopped, results = event
            finished = True
            self._finish_batch_task(completed, total, stopped, results, None)
        elif kind == "error":
            _kind, completed, total, exc, detail, results = event
            finished = True
            self._finish_batch_task(completed, total, True, results, (exc, detail))

        if not finished and batch_poll_should_yield(processed_events, poll_started):
            yielded = True
            break

    if self._batch_active and not finished:
        # Yield to Tk.
        delay = SATURATED_BATCH_POLL_DELAY_MS if yielded else 80
        self._batch_poll_job = self.after(delay, self._poll_batch_queue)


def _finish_batch_task(
    deps: BatchWorkflowDeps, self, completed: int, total: int, stopped: bool, results, error) -> None:
    callback = self._batch_on_done
    title = self._batch_title
    self._batch_active = False
    self._batch_in_item = False
    self._batch_parallel = False
    self._batch_pause_event.set()
    self.batch_pause_button.configure(text="暂停", state="disabled")
    self.batch_stop_button.configure(text="停止", state="disabled")
    if error is None:
        self.batch_progress_var.set(100.0 * completed / max(1, total))
        if stopped:
            self.batch_text_var.set(f"{title}：已停止，完成 {completed}/{total}")
            self.status_var.set(f"{title}已安全停止：已完成 {completed}/{total} 页，已完成结果均已保留。")
        else:
            self.batch_text_var.set(f"{title}：完成 {completed}/{total}")
    else:
        exc, detail = error
        self.batch_text_var.set(f"{title}：发生错误，完成 {completed}/{total}")
        print(detail)
        self.show_error(f"{title}失败", exc)

    if callback is not None:
        try:
            callback(completed, total, stopped, results, error)
        except Exception as callback_exc:
            self.show_error(f"{title}完成处理失败", callback_exc)

    self._batch_thread = None
    self._batch_on_done = None
    self._batch_title = ""
    self._batch_foreground_pages = False
    self._batch_allow_page_navigation = False
    self._batch_allow_pdic_edits = False
    with self._batch_state_lock:
        self._batch_page_states = {}
    if getattr(self, "_batch_refresh_page_quality", True):
        self._refresh_page_quality_colors()
    self._batch_refresh_page_quality = True
    self.after(1800, self._hide_batch_bar_if_idle)
    if self._batch_close_after_stop:
        self._batch_close_after_stop = False
        self.after_idle(self.on_close)


def _hide_batch_bar_if_idle(
    deps: BatchWorkflowDeps, self) -> None:
    if not self._batch_active and not self._ui_worker_key_active("crop-width-normalization") and self.batch_bar.winfo_manager():
        self.batch_bar.pack_forget()


def _toggle_batch_pause(
    deps: BatchWorkflowDeps, self) -> None:
    if not self._batch_active:
        return
    if self._batch_pause_event.is_set():
        self._batch_pause_event.clear()
        self.batch_pause_button.configure(text="继续")
        if getattr(self, "_batch_in_item", False):
            self.batch_text_var.set(f"{self._batch_title}：暂停请求已发出")
            if getattr(self, "_batch_parallel", False):
                self.status_var.set("暂停请求已发出：不再派发新页面；已启动的并行页面完成后暂停。")
            else:
                self.status_var.set("暂停请求已发出：当前页处理完成后暂停，不会中断正在写入的文件。")
        else:
            self.batch_text_var.set(f"{self._batch_title}：已暂停")
            self.status_var.set("批量任务已暂停；点击“继续”恢复。")
    else:
        self._batch_pause_event.set()
        self.batch_pause_button.configure(text="暂停")
        self.batch_text_var.set(f"{self._batch_title}：继续处理中…")
        self.status_var.set("批量任务继续运行。")


def _request_batch_stop(
    deps: BatchWorkflowDeps, self) -> None:
    if not self._batch_active:
        cancel = getattr(self, "_crop_width_cancel_event", None)
        if cancel is not None:
            cancel.set()
            self.batch_stop_button.configure(state="disabled")
            self.status_var.set("PNG 宽度标准化：已请求取消，当前图片完成后停止")
        return
    self._batch_stop_event.set()
    # Wake a task that is currently paused so the worker can observe stop.
    self._batch_pause_event.set()
    self.batch_pause_button.configure(state="disabled")
    self.batch_stop_button.configure(state="disabled")
    self.batch_text_var.set(f"{self._batch_title}：停止请求已发出")
    if getattr(self, "_batch_parallel", False):
        self.status_var.set("停止请求已发出：不再派发新页面；已启动页面完成后安全停止，已完成结果保留。")
    else:
        self.status_var.set("停止请求已发出：当前页处理完成后安全停止；已完成页面结果会保留。")



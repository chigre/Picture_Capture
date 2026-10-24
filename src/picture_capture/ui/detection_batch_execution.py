"""Ordinary/OCR/combined multi-page detection orchestration.

Preserves the original app's single-writer PDIC execution, resume and
manual PPP protections, batched CPU/GPU planning, progress callbacks and
error/status reporting. All app global patch seams are passed at call time.
"""
from __future__ import annotations
from typing import Any


def detect_pages(self, indices: list[int], *, method: str, force_refresh: bool, deps: dict[str, Any]) -> None:
    messagebox = deps["messagebox"]
    replace = deps["replace"]
    os = deps["os"]
    headword_filter_rules_path = deps["headword_filter_rules_path"]
    HEADWORD_FILTER_RULES_FILENAME = deps["HEADWORD_FILTER_RULES_FILENAME"]
    ProcessPoolExecutor = deps["ProcessPoolExecutor"]
    multiprocessing = deps["multiprocessing"]
    project_profile_path = deps["project_profile_path"]
    replace_rules_path = deps["replace_rules_path"]
    pdic_path = deps["pdic_path"]
    ocr_cache_root = deps["ocr_cache_root"]
    normalize_page_rgb = deps["normalize_page_rgb"]
    read_page_sections = deps["read_page_sections"]
    detect_entries = deps["detect_entries"]
    ocr_existing_entry_words_from_markers = deps["ocr_existing_entry_words_from_markers"]
    load_replace_rules = deps["load_replace_rules"]
    write_pdic = deps["write_pdic"]
    detect_entries_job = deps["detect_entries_job"]
    statistics = deps["statistics"]
    Image = deps["Image"]
    if method == "left_edge":
        # One physical page must never be submitted to multiple writer
        # processes in the same batch, even through an unusual API caller.
        indices = list(dict.fromkeys(indices))
    if not self.project or not indices:
        self.status_var.set("没有需要处理的页面"); return
    if not self._guard_transformed_geometry("批量画线"):
        return
    label = {
        "combined": "融合画线",
        "paddleocr": "OCR画线",
        "left_edge": "普通画线",
    }.get(method, "画线")
    if len(indices) > 1 and not messagebox.askyesno(
        label,
        f"将对 {len(indices)} 页执行{label}并重写这些页面的 PDIC 画线。\n\n"
        "处理期间会显示进度，可暂停或停止；暂停/停止会在当前页完成后安全生效。继续？",
        parent=self,
    ):
        return
    from ..layout.mask_source_guard import missing_saved_illustrations, detection_mask_source_path
    missing_ppp = missing_saved_illustrations(
        (self.project.images[i] for i in indices), self.settings,
    )
    if missing_ppp:
        names = "、".join(page.name for page in missing_ppp[:4])
        suffix = f" 等 {len(missing_ppp)} 页" if len(missing_ppp) > 4 else ""
        message = (f"这些页面缺少已保存的 PPP 插图数据：{names}{suffix}。\n"
                   "请先运行插图识别，或在设置中心→插图关闭‘使用已有的插图数据’。\n"
                   "本次画线未开始，其他页面的 PDIC 不会被部分覆盖。")
        self.status_var.set(message)
        messagebox.showerror("Layout 插图复用检查失败", message, parent=self)
        return
    import time
    batch_started_at = time.time()
    self.save_pdic(silent=True)
    # Auto illustration detection persists PPP in workers. Flush any
    # foreground manual edits first so the worker's AUTO merge preserves
    # them. PPP-reuse mode is read-only and must never fabricate a missing
    # PPP file.
    if (
        method == "left_edge"
        and bool(getattr(self.settings, "layout_mask_illustrations", False))
        and not bool(getattr(self.settings, "layout_mask_illustrations_use_existing", False))
        and self.current_page is not None
    ):
        from ..io.formats import write_ppp
        self._sync_polygon_label_texts()
        self._save_normalized_ppp()
    self.settings.detection_method = method
    settings = replace(self.settings)
    # Set the process environment *before* spawning workers. Snapshot the
    # values at the start of this batch to keep child processes consistent.
    os.environ["PICTURE_CAPTURE_DRAW_PROFILE"] = (
        "1" if bool(getattr(settings, "draw_performance_profile", False)) else "0"
    )
    os.environ["PICTURE_CAPTURE_REUSE_PREPARED_ANALYSIS"] = (
        "1" if bool(getattr(settings, "reuse_prepared_analysis", False)) else "0"
    )
    project = self.project
    pages_info = {i: self.pages_tuple(i) for i in indices}
    filter_path = headword_filter_rules_path(project.root, HEADWORD_FILTER_RULES_FILENAME)
    from ..ordinary.parallel import ordinary_draw_workers
    ordinary_workers = (
        ordinary_draw_workers(len(indices)) if method == "left_edge" else 1
    )
    from ..ordinary.gpu_pipeline import staged_pipeline_enabled
    from ..ordinary.cpu_pool import cpu_pool_enabled, cpu_pool_config
    cpu_pool = bool(
        method == "left_edge"
        and cpu_pool_enabled(settings, len(indices))
    )
    cpu_pool_workers, cpu_inference_threads = (
        cpu_pool_config(len(indices)) if cpu_pool else (1, 1)
    )
    # CPU-only takes priority over staged GPU mode.
    gpu_staged = bool(
        method == "left_edge" and not cpu_pool
        and staged_pipeline_enabled(settings, len(indices))
    )
    if cpu_pool:
        ordinary_workers = cpu_pool_workers
    elif gpu_staged:
        # Never duplicate CUDA models across workers.
        ordinary_workers = 2
    normal_executor = (
        ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn"))
        if method == "left_edge" and ordinary_workers <= 1 else None
    )

    def worker(index: int, _position: int, _total: int):
        page = project.images[index]
        from ..quality.draw_performance_profile import enabled as profile_enabled, record_page
        tracing = profile_enabled() and method in {"paddleocr", "combined"}
        stages = {}
        trace_tick = time.perf_counter()
        resume_dependencies = ()
        if (
            method in {"paddleocr", "combined"}
            and settings.ocr_resume_completed_pages
            and not force_refresh
        ):
            from ..persistence.project_storage import page_sections_read_path_for_image
            from ..ocr.page_resume import validated_resume
            resume_dependencies = (
                filter_path,
                project_profile_path(project.root),
                page_sections_read_path_for_image(page),
                *( (replace_rules_path(project.root),) if method == "combined" else () ),
            )
            saved = pdic_path(page)
            previous_count = validated_resume(
                ocr_cache_root(project.root), page, saved,
                page_index=index, method=method, settings=settings,
                dependencies=resume_dependencies,
            )
            if previous_count is not None:
                return {"index": int(index), "count": previous_count, "resumed": True}
        if normal_executor is not None:
            if cpu_pool:
                from ..ordinary.cpu_pool import cpu_ordinary_page_job
                count = normal_executor.submit(
                    cpu_ordinary_page_job, str(page), settings,
                    pages_info[index], index, cpu_inference_threads,
                ).result()
            else:
                count = normal_executor.submit(
                    detect_entries_job, str(page), settings, pages_info[index], index
                ).result()
            return {"index": int(index), "count": int(count)}
        with Image.open(page) as opened:
            image = normalize_page_rgb(opened)
        if tracing:
            stages["ocr_image_load"] = time.perf_counter() - trace_tick
            trace_tick = time.perf_counter()
        cache_path = ocr_cache_root(project.root) / f"{page.stem}.json" if method in {"paddleocr", "combined"} else None
        sections = read_page_sections(page)
        entries, _geometry = detect_entries(
            image, settings, paddle_cache_path=cache_path,
            force_paddle_refresh=force_refresh,
            paddle_filter_rules_path=filter_path,
            profile_page_index=index,
            page_sections=sections,
            source_image_path=detection_mask_source_path(
                page, settings, ordinary=method == "left_edge",
            ),
        )
        if tracing:
            stages["ocr_detect_entries"] = time.perf_counter() - trace_tick
            trace_tick = time.perf_counter()
        text_stats = None
        if method == "combined":
            original_coords = [
                (int(entry.x), int(entry.y)) for entry in entries
            ]
            entries, text_stats = ocr_existing_entry_words_from_markers(
                image,
                entries,
                settings,
                load_replace_rules(replace_rules_path(project.root)),
                profile_page_index=index,
                page_sections=sections,
                profile_path=project_profile_path(project.root),
                only_blank=True,
            )
            if [
                (int(entry.x), int(entry.y)) for entry in entries
            ] != original_coords:
                raise RuntimeError(
                    f"{page.name} 融合画线自动补字意外修改了画线坐标"
                )
        if tracing:
            stages["ocr_marker_text_fill"] = time.perf_counter() - trace_tick
            trace_tick = time.perf_counter()
        saved_pdic = pdic_path(page)
        if method in {"paddleocr", "combined"}:
            # Preserve manual PDIC before automated OCR overwrites it.
            from ..ocr.pdic_preservation import preserve_prior_pdic
            preserve_prior_pdic(project.root, page, saved_pdic)
        write_pdic(saved_pdic, entries, image.width, pages_info[index])
        if tracing:
            stages["ocr_preserve_and_pdic"] = time.perf_counter() - trace_tick
            trace_tick = time.perf_counter()
        result = {"index": int(index), "count": len(entries)}
        if method in {"paddleocr", "combined"} and cache_path is not None:
            # The OCR cache is pre-Layout. Read the *actual saved PDIC*
            # and record final moves/removals/rescues separately. This
            # audit never modifies PDIC and failure must not lose a page.
            try:
                from ..ocr.final_decisions import record_final_decisions
                result["final_audit"] = record_final_decisions(
                    cache_path, saved_pdic, entries,
                    tolerance=max(5, round(settings.character_height * 0.45)),
                )
            except (OSError, ValueError, TypeError) as exc:
                result["final_audit_error"] = f"{type(exc).__name__}: {exc}"
        if method in {"paddleocr", "combined"} and settings.ocr_resume_completed_pages:
            if not resume_dependencies:
                # A forced OCR rerun bypasses prior checkpoints but still
                # writes a *new* completed checkpoint for later resumption.
                from ..persistence.project_storage import page_sections_read_path_for_image
                resume_dependencies = (
                    filter_path,
                    project_profile_path(project.root),
                    page_sections_read_path_for_image(page),
                    *((replace_rules_path(project.root),) if method == "combined" else ()),
                )
            from ..ocr.page_resume import write_page_resume
            try:
                write_page_resume(
                    ocr_cache_root(project.root), page, pdic_path(page),
                    page_index=index, method=method, settings=settings,
                    marker_count=len(entries), dependencies=resume_dependencies,
                )
            except (OSError, ValueError, TypeError) as exc:
                result["resume_checkpoint_error"] = f"{type(exc).__name__}: {exc}"
        if text_stats:
            result.update({
                "text_filled": int(text_stats.get("filled", 0)),
                "text_regular": int(text_stats.get("regular", 0)),
                "text_large": int(text_stats.get("large", 0)),
                "text_failed": int(text_stats.get("failed", 0)),
            })
        if tracing:
            stages["ocr_audit_resume"] = time.perf_counter() - trace_tick
            record_page(page, index, stages, mode=method)
        return result

    def done(completed, total, stopped, results, error):
        if normal_executor is not None:
            normal_executor.shutdown(wait=False, cancel_futures=True)
        if error is not None:
            return
        self.load_page(self.current_index)
        quality_text = ""
        if method in {"paddleocr", "combined"}:
            self._refresh_page_quality_colors()
            quality_text = "；页面列表已按 OCR 一致性/质量状态更新"
            resumed = sum(
                1 for row in results if isinstance(row, dict) and row.get("resumed")
            )
            if resumed:
                quality_text += f"；经完整校验断点跳过 {resumed} 页"
            checkpoint_failures = sum(
                1 for row in results
                if isinstance(row, dict) and row.get("resume_checkpoint_error")
            )
            if checkpoint_failures:
                quality_text += f"；{checkpoint_failures} 页无法记录恢复点"
            final_stats = [
                row.get("final_audit")
                for row in results
                if isinstance(row, dict) and isinstance(row.get("final_audit"), dict)
            ]
            if final_stats:
                quality_text += (
                    f"；最终PDIC对齐 {sum(int(v.get('linked', 0)) for v in final_stats)} 条"
                    f"，Layout等独立候选 {sum(int(v.get('unmatched_final', 0)) for v in final_stats)} 条"
                )
            audit_errors = sum(
                1 for row in results
                if isinstance(row, dict) and row.get("final_audit_error")
            )
            if audit_errors:
                quality_text += f"；{audit_errors} 页最终决策记录未能保存（PDIC已保存）"
            if method == "combined":
                filled = sum(
                    int((row or {}).get("text_filled", 0))
                    for row in results
                )
                regular = sum(
                    int((row or {}).get("text_regular", 0))
                    for row in results
                )
                large = sum(
                    int((row or {}).get("text_large", 0))
                    for row in results
                )
                failed = sum(
                    int((row or {}).get("text_failed", 0))
                    for row in results
                )
                quality_text += (
                    f"；普通救漏自动补字 {filled} 条"
                    f"（普通框 {regular}，大字框 {large}，未识别 {failed}）"
                )
        else:
            rows = [
                value for value in results
                if isinstance(value, dict)
                and isinstance(value.get("count"), (int, float))
                and int(value.get("count", -1)) >= 0
            ]
            counts = [int(row["count"]) for row in rows]
            median_count = float(statistics.median(counts)) if counts else 0.0
            suspect_rows: list[dict] = []
            for row in rows:
                count = int(row["count"])
                if count == 0:
                    suspect_rows.append(row)
                elif len(counts) >= 5 and median_count >= 8:
                    if count < median_count * 0.45 or count > median_count * 1.80:
                        suspect_rows.append(row)
            if counts:
                quality_text = f"；每页画线数中位数 {median_count:g}"
            if suspect_rows:
                names = [
                    project.images[int(row["index"])].name
                    for row in suspect_rows[:3]
                    if 0 <= int(row.get("index", -1)) < len(project.images)
                ]
                more = "…" if len(suspect_rows) > 3 else ""
                quality_text += (
                    f"；{len(suspect_rows)} 页画线数异常，建议优先复核"
                    + (f"（{', '.join(names)}{more}）" if names else "")
                )
        from ..quality.inference_monitor import recent_model_events
        elapsed_seconds = max(0.001, time.time() - batch_started_at)
        observed_events = recent_model_events(batch_started_at)
        observed_devices = sorted({str(row["device"]) for row in observed_events})
        observed_pids = {int(row["pid"]) for row in observed_events}
        inferred = "/".join(observed_devices) if observed_devices else "未记录（可能命中缓存）"
        monitor_text = (
            f"；耗时 {elapsed_seconds:.1f}s"
            f"；速度 {completed / elapsed_seconds:.2f} 页/s"
            f"；模型设备 {inferred}"
            f"；模型实例进程 {len(observed_pids)}"
        )
        if cpu_pool:
            monitor_text += f"；CPU 工作进程配置 {cpu_pool_workers}"
        elif gpu_staged:
            monitor_text += "；GPU 推理生产者 1 / CPU 消费者最多 2"
        elif method in {"paddleocr", "combined"}:
            monitor_text += "；OCR 页面串行调度"
        if observed_events:
            observed_dnn = sorted({
                str(row["mkldnn"]) for row in observed_events
                if row.get("device") == "cpu"
            })
            if observed_dnn:
                monitor_text += f"；oneDNN 配置 {'/'.join(observed_dnn)}"
        quality_text += monitor_text
        from ..quality.draw_performance_profile import (
            enabled as profiling_enabled, recent_profiles, export_batch_report,
        )
        if profiling_enabled():
            page_names = {str(project.images[i]) for i in indices}
            stage_rows = recent_profiles(batch_started_at, pages=page_names)
            try:
                report_path = export_batch_report(
                    stage_rows, label=label, elapsed_seconds=elapsed_seconds,
                    completed=completed, settings=settings,
                )
            except Exception as exc:
                quality_text += f"；性能报告导出失败：{exc}"
            else:
                quality_text += (
                    f"；性能报告已保存：{report_path}"
                    if stage_rows else
                    f"；性能报告已保存（没有匹配到逐页计时数据）：{report_path}"
                )
        suffix = "（强制重新识别）" if method in {"paddleocr", "combined"} and force_refresh else ""
        skipped = int(getattr(self, "_batch_skipped_count", 0))
        skip_text = f"，人工锁定跳过 {skipped} 页" if skipped else ""
        if stopped:
            self.status_var.set(
                f"{label}{suffix}已停止：处理进度 {completed}/{total}{skip_text}；"
                f"结果已保留{quality_text}"
            )
        else:
            self.status_var.set(
                f"{label}{suffix}完成：{completed}/{total}{skip_text}{quality_text}"
            )

    if gpu_staged:
        from ..ordinary.gpu_pipeline import (
            prepare_gpu_layout_job, detect_entries_staged_job,
        )
        started = self._start_parallel_batch_task(
            label, indices, detect_entries_staged_job,
            lambda index, _position, _total: (
                str(project.images[index]), settings, pages_info[index], index,
            ),
            result_consumer=lambda index, count: {
                "index": int(index), "count": int(count),
            },
            on_done=done,
            item_label=lambda index: project.images[index].name,
            max_workers=ordinary_workers,
            foreground_page_edit=True,
            page_indexer=lambda index: int(index),
            gpu_preflight_func=prepare_gpu_layout_job,
            gpu_job_builder=lambda index, _position, _total: (
                str(project.images[index]), settings, index,
            ),
        )
    elif cpu_pool and cpu_pool_workers > 1:
        from ..ordinary.cpu_pool import cpu_ordinary_page_job
        started = self._start_parallel_batch_task(
            label, indices, cpu_ordinary_page_job,
            lambda index, _position, _total: (
                str(project.images[index]), settings,
                pages_info[index], index, cpu_inference_threads,
            ),
            result_consumer=lambda index, count: {
                "index": int(index), "count": int(count),
            },
            on_done=done,
            item_label=lambda index: project.images[index].name,
            max_workers=cpu_pool_workers,
            foreground_page_edit=True,
            page_indexer=lambda index: int(index),
        )
    elif method == "left_edge" and ordinary_workers > 1:
        # Dormant legacy parallel path: the ordinary_draw_workers safety
        # policy always returns 1 unless a separately validated design
        # deliberately changes it. No duplicate GPU inference permitted.
        started = self._start_parallel_batch_task(
            label, indices, detect_entries_job,
            lambda index, _position, _total: (
                str(project.images[index]), settings, pages_info[index], index,
            ),
            result_consumer=lambda index, count: {
                "index": int(index), "count": int(count),
            },
            on_done=done,
            item_label=lambda index: project.images[index].name,
            max_workers=ordinary_workers,
            foreground_page_edit=True,
            page_indexer=lambda index: int(index),
        )
    else:
        started = self._start_batch_task(
            label, indices, worker, done,
            item_label=lambda index: project.images[index].name,
            foreground_page_edit=True, page_indexer=lambda index: int(index),
        )
    if not started and normal_executor is not None:
        normal_executor.shutdown(wait=False, cancel_futures=True)

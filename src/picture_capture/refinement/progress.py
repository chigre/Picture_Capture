"""Compact GUI/CMD reporting for per-page Y-refinement evidence."""


def report_refinement_page(ui, completed: int, total: int, label: str,
                           result: dict) -> None:
    """Report actual Layout invocations, unchanged PDIC, or explicit skips."""
    if result.get("skipped"):
        detail = str(result.get("reason", "未知原因"))
        ui.batch_text_var.set(f"精修画线：{completed}/{total}，跳过 {label}")
        ui.status_var.set(f"精修跳过 {label}：{detail[:180]}")
        print(f"[精修画线][SKIPPED] {label}: {detail}", flush=True)
        return
    measured = int(result.get("layout_measured", 0))
    mode = str(result.get("mode", "unknown"))
    saved = int(result.get("saved", 0))
    layout_source = str(result.get("layout_source", "unknown"))
    ui.status_var.set(
        f"精修 {completed}/{total}：{label}；"
        f"版面路径 {layout_source}；处理 {measured} 次；PDIC更新 {saved} 次；模式 {mode}"
    )
    print(
        f"[精修画线][PAGE] {label}: mode={mode}"
        f" layout_measured={measured} layout_source={layout_source}"
        f" pdic_saved={saved}",
        flush=True,
    )

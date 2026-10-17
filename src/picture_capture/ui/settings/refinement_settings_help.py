"""Precise, isolated UI help for manual Y refinement and shared separator checks.

Kept out of the broad settings schema so the 100 kB architecture ceiling
is respected without deleting documented behavior or weakening the guard.
"""

REFINEMENT_SETTING_HELP = {
        "paddle_separator_search_ratio": "作用：自动画线的局部空白谷搜索半径；点击【精修画线】时则从已有 PDIC 横线向上和向下查找首行墨迹，范围按行高乘该比例（0.05–0.80）并结合硬性最大位移计算。\\n\\n它只决定观察范围，不规定最终落线位置。精修按钮不重新运行 OCR 或完整 LAYOUT。",
        "paddle_separator_band_radius": "作用：自动 OCR／普通画线空白谷墨迹曲线的平滑半径，单位为像素。【精修画线】是全栏白行优先，只有值大于 0 时桥接词头局部墨迹检测中的 1px 小断点；并不会对真实字顶位置做平滑。\\n\\n不是空白宽度，也不是横线与字顶的固定距离。",
        "paddle_separator_safety_px": "作用：点击【精修画线】时，在首行文字上缘与所选空白横线之间保留的**最小**距离（原图 px，最少 1px）。程序向上、向下查找词头首行，再检查整栏宽度及候选 Y 上下相邻行的墨迹，优先选择整栏近白、接近字顶安全距离的 Y；若没有合适的白行，再选择整栏墨迹分布中明显的局部谷底；没有可靠谷底才保留原 Y。\\n\\n不是固定的『字顶 Y 减 N 像素』；数值越大允许的贴字程度越低。某些 OCR 边界处理还会读取此字段，但不代表全部自动画线使用统一间距。",
        "paddle_separator_roi_width_ratio": "作用：自动画线按指定单栏百分比采样局部墨迹；主动【精修画线】则用此比例限制从已保存 PDIC 词条 X 起的**短词头区域**，只负责判断当前首行的字顶。\\n\\n确定最终落线位置时，普通及快速精修统一检查**栏宽向两侧各扩半栏间距**的墨迹（并避开相邻栏正文），而不只看词头附近是否空白。这是避免右侧释文／较高笔画被横线切穿的关键。",
        "separator_y_max_shift_ratio": "作用：限制精修相对原始 PDIC Y 的最大上下移动量，默认 0.45 倍行高。即便在更远处找到整栏白行，也不能跨越本设置的硬性位移上限。与【横线搜索半径】不同。\\n\\n设置为 0 时主动精修不移动；设大可能找到更合适的全栏空白 Y，但增加选中邻行的风险。",
        "paddle_separator_column_margin": "作用：精修时从含半栏距扩展的物理区域两端排除少量栏线／装订阴影后，横向检查其余墨迹。为避免隐藏真正正文，主动精修最多排除单栏宽度的 10%。\\n\\n减小可覆盖更多靠边字迹，增大可能避开真实竖边框；不是 Y 方向的留白距离。",
}

REFINEMENT_CHECK_HELP = {
        "paddle_refine_separator_y": "自动普通画线／OCR 等共用画线路径的 Y 精修和原图白缝墨迹安全检查，统一由这一个开关控制。开启时先进行局部墨迹谷精修，再依据下方四项白缝阈值核验；关闭时两步都不运行。旧项目的 separator_y_ink_safe_gap 字段仅兼容读取，不再独立控制功能。\\n\\n用户主动点击【精修画线】仍独立处理已有 PDIC 横线（包括人工线），优先选择词条字顶上方近白行，没有合适白行时选择可信的墨迹谷底；不重新 OCR、不增删词条。启用自动版面参数时可复用当前页 LayoutRows JSON 的有效物理参数。",
}

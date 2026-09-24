# Project Profile 经典词头局部样例包

本目录保存 Project Profile 向导实际使用的经典词头局部样例。

## recommended_current
当前 9 张图片与 `dictionary_profiles_v3.json` 中的 `validated_examples` 一一对应。程序会先兼容查找 `headword_examples/` 根目录中的同名资源，再读取 `recommended_current/`；若单张样例缺失，则回退到 `classic_headword_examples.jpg` atlas 裁切。

## 原则
- 均为真实测试词典页面的局部裁切，不使用整页缩略图替代。
- 每张保留 1–数个完整词头及少量相邻释义，使“哪里是新词条”一眼可见。
- 自定义结构不放固定经典样例，因为它定义上就是预设无法覆盖的版式。
- `manifest.csv/json` 仅记录当前实际保留并可被程序使用的 `recommended_current` 样例及来源。

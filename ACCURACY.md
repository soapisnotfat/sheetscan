# Automatic recognition for practice scores

用户的首要需求是：导入 PDF 后，直接得到完整、可练习的谱面，准确率至少达到 99.5%，目标 99.9%。疑点确认、修改音符和拖动音符是兜底功能。不能用大量人工校对来代替自动识别的准确度。

当前尚未证明达到这个目标。Dripping 的 tempo 修改和 PDF 集成已暂停，准确度研究在此 fork 独立进行。

## 先验证什么

首批场景是印刷五线谱，重点覆盖萨克斯旋律谱及其钢琴声部：多页、封面、变拍号、弱起、二连音／三连音／五连音、附点、倚音、延音线、临时升降号、合并休止和反复顺序。

“音高识别对”不能代替“谱子识别对”。核心事件必须同时匹配记谱音高、所在小节、拍内位置、时值、声部、延音和连音比例；休止也计入。另行检查声部／小节数量、拍号、反复和明确印出的数字 tempo。整曲不需要修正的比例也要单独报告。

`bench/practice_metrics.py` 提供核心事件的严格比较，不把错位的小节重新对齐来抬高分数。`--gate .995` 要求事件 precision、recall 均达到阈值，并通过结构、拍号、反复和适用的 tempo 检查。它尚未覆盖所有演奏法、力度、歌词和排版细节，不能单独作为“整份乐谱所有元素 99.5%”的认证。

仅供 MIDI 播放的隐藏音符、隐藏休止和未印出的 tempo 不应被当作 PDF 可识别的内容；报告会列出这类排除项。未印数字 tempo 时必须保留未知状态，不能凭空填一个数当作识别成功。

人工修改后的结果不计作自动准确率。拒识和需要确认的内容不能从分母里悄悄删掉。XML 格式合法、时值恰好填满小节、模型自己给出高分，都不等于答案正确。

## 已有证据与本轮修改

- 此前本地批测包含 10 份 PDF、40 个所选页面，主要验证结构与导出稳定性；尚无这批完整谱的独立逐音标准答案，不能据此报出准确率。
- 复查一个真实二连音错例，发现当前 homr 的节奏编码不能直接表达该 2:3 时值。单纯更换 Worker 或 GPU 不会补上这个表达能力。
- 新增基于原图字形、音符位置和拍号的 2:3／5:4 连音候选。仅处理有明确印刷数字、唯一匹配音组且整小节时值一致的情况；不只靠“把小节填满”。候选保留原图坐标、涉及音符、原始时值、建议时值以及保留原结果的选项。
- 自动应用策略目前通过 `--printed-tuplets` 或浏览器 `?printed-tuplets=1` 显式开启。先验证策略本身，再决定默认启用条件。低把握或冲突的情况保留为确认候选，不伪造概率。
- 修复 homr 在小节开头生成 forward repeat 却标为右侧小节线的问题；只修正位于本小节音符之前的这一明确矛盾。
- 修复同组文字中只保留第一处数字 tempo 的问题，并把速度标记定位到临近音符；只出现 Allegro 等文字时保留原文，不再伪造一个精确 BPM。
- 新增自建 21 小节、50 个非倚音事件的标准答案挑战谱，包含 6/8、2/4、3/8、4/4、二／三／五连音、数字 tempo 变化、11 小节休止和反复。该旋律为自建 CC0 测试内容，标准答案来自生成器，不来自识谱输出。

这个小型挑战谱用于定位和回归，已经看过并用来修改代码，属于开发集。即使全部通过，也不能替代未参与开发的完整谱测试集。

[本轮报告](bench/results/development-2026-11-15.json)：完整浏览器流程在自建挑战谱上匹配 50/50 个非倚音事件、1/1 个倚音、21/21 小节，且拍号、反复与两处数字 tempo 均匹配。公开 Bach 样本的原生结果匹配 165/165 个可见记谱事件。模型权重未重训；这些结果只证明列出的开发用例，不是实际谱库 99.5% 的证明。

## 自动识别的改进顺序

1. 从完整 PDF 到完整 MusicXML 建立基线。将字体、图像分辨率、扫描噪声、符号布局和跨页错误分别记录；用独立校对的 MusicXML 作标准答案。按整首曲目划分开发集和保留测试集，不能把同一曲的相邻页面分到两边。
2. 保留模型候选与原图证据，结合全曲的调号、拍号、声部和时值约束重新判断。优先修复已定位的表达／导出错误，不为满足小节长度随意改音。
3. 在同一测试集比较不同识别模型，必要时结合独立模型复核分歧小节。多数票本身不能保证正确；只保留实际降低错误且不引入回归的策略。
4. 如果错误集中在当前模型无法表达或训练不足的符号，再修改输出编码、训练目标和数据。针对实际字体与萨克斯谱的合成数据和独立标注数据微调，并保留未参与训练的测试谱。
5. 准确度合格后再优化浏览器启动、内存和速度。WASM、WebGPU、量化和批处理的每项改动都重新比较最终乐谱，不能用速度收益掩盖识别回归。

当前 homr 是可运行的浏览器基线；[其训练记录](https://github.com/liebharc/homr/blob/main/Training.md)提供模型实验与系统级验证。另需实际对比 [copisteria](https://github.com/kobimusic/copisteria) 的页面上下文方案，以及 [Legato](https://arxiv.org/abs/2506.19065) 的整页识别方案。这些是研究候选，尚未在本项目的标准答案测试集上验证，也尚未证明适合目标浏览器的内存与推理预算。

## 复现

原有原生识谱环境需要 homr 及其模型；浏览器依赖使用 `web/package-lock.json`。原生数字 OCR 的可选 `--read-numbers` 复用本机 Tesseract 命令；浏览器使用已有的 Tesseract.js，不要求最终用户安装 Python。

```sh
python -m unittest discover -s bench -p 'test_*.py'
python bench/make_practice_case.py
cd web
npm ci
node --test tools/annotation.test.mjs
node tools/render-practice-case.mjs ../dev-samples/accuracy/challenge/truth.musicxml
cd ..
pdftoppm -r 200 -singlefile -png dev-samples/accuracy/challenge/score.pdf dev-samples/accuracy/challenge/pdf-p1
python bench/recognize_case.py dev-samples/accuracy/challenge/reading.musicxml dev-samples/accuracy/challenge/pdf-p1.png --read-numbers --printed-tuplets
python bench/practice_metrics.py dev-samples/accuracy/challenge/truth.musicxml dev-samples/accuracy/challenge/reading.musicxml --gate .995
```

渲染脚本需要 Playwright Chromium，或设置 `PLAYWRIGHT_CHANNEL=chrome` 使用已有 Chrome。每次测试使用独立浏览器资料，不读取个人浏览器资料。

原生运行不含浏览器的 PDF.js 与文本注释阶段，不能当作最终网页流程的结果。完整浏览器测试：

```sh
cd web
npm run dev
# 在另一终端运行；端口按实际 dev 地址填写
node tools/browser-test.mjs chromium http://localhost:5173/ --input=../dev-samples/accuracy/challenge/score.pdf --output=../dev-samples/accuracy/challenge/browser.musicxml --printed-tuplets
cd ..
python bench/practice_metrics.py dev-samples/accuracy/challenge/truth.musicxml dev-samples/accuracy/challenge/browser.musicxml --gate .995
```

原始私人 PDF、音频、标注和中间结果保留在本机忽略目录。`bench/results/` 只保存可公开测试的报告摘要。源代码和上游许可保持公开；Bravura 生成字形遵循现有 OFL 许可。

# 解析开关与模式的源码调研

日期：2026-10-08。范围：已提交代码 `58cc6e00`，以及工作区已有但未提交的公式开关改动。本次没有修改功能代码，没有提交任务到部署服务，也没有执行模型质量验收。

后续用户已授权公式开关开发并更新原 PR。本页保留调研时点的证据；迭代实现与最新测试见[公式迭代验证](2026-10-08-formula-options-validation.md)。

工作区已有 formula_enable 改动。本报告不将这些改动视为已发布功能，也不将其静态行为视为验收通过。

## OCR 模式

API 的合法值是 auto、txt、ocr，没有 force 或 disable。

- auto：调用 PDFDocument.classify()，得到文档级 txt 或 ocr。此处不能解释为逐页自动切换。
- txt：正文主要使用 PDF 自带文字。仍执行部分布局、文字检测和补充 OCR，不能解释为禁止所有 OCR。表格、公式、图片分析也不因 txt 自动关闭。
- ocr：通过页面图像提取文字。basic 使用本地 OCR；standard 和 advanced 主要使用视觉语言模型提取正文，并保留本地文字检测等处理。
- 图片先进入 PDF 路径。图片没有可用文字层时，不应把 txt 当作可靠的扫描文字提取方式；auto 或 ocr 更符合输入特点。具体补充识别效果需实测。

源码：parser/api_server.py:CreateJobRequest；backend/analysis/pdf/pipeline.py:_prepare_analysis；backend/analysis/pdf/ocr.py:_build_ocr_det_type_and_mfr_enable；backend/analysis/pdf/text/content.py:_fill_window_block_content_and_lines。

## 解析等级

| 等级 | txt | ocr | table_enable=false | image_analysis=true |
| --- | --- | --- | --- | --- |
| flash | 原生 PDF 提取路径 | 本地布局和 OCR，含表格内容处理 | 明确拒绝 | 不启用图片语义分析 |
| basic | 本地布局，正文主要使用原生文字 | 本地布局和 OCR | 支持，表格区域改为图片 | 不启用图片语义分析 |
| standard | 本地布局，正文主要使用原生文字，视觉模型处理其余区域 | 本地布局，视觉模型提取正文等内容 | 支持，表格区域改为图片 | 不启用图片语义分析 |
| advanced | 视觉模型处理布局及视觉区域，正文主要使用原生文字 | 视觉模型提取布局和内容 | 支持，表格区域改为图片 | 启用图片语义分析 |

auto 的行为对应其最终解析出的 txt 或 ocr。等级映射为 flash/flash、basic/medium、standard/high、advanced/xhigh。

## 表格开关

basic、standard、advanced 的 PDF/图片路径均支持关闭表格。关闭后保留检测到的表格区域，停止结构化表格抽取，排除完整位于表格内部的正文、公式和图片子块，最后将表格转换为图片。题注独立保留。

txt 下，basic 和 standard 在表格开启时还有原生表格优先处理。因此，同一表格在 txt 与 ocr 下可能走不同提取路径，单元格文字和结构结果不保证相同。

advanced 关闭表格时改用先布局、再按布局抽取的流程，避免图片分析重新解释该表格区域。该规则受布局检测质量约束；漏检表格、部分重叠区域仍需真实样本验证。

## 图片分析开关

只有 advanced 将请求的 image_analysis 传给视觉模型；standard 在该位置固定传 false，basic、flash 不执行这类图片语义分析。开关控制图片解释，不控制是否保存图片，也不是普通文字 OCR 的总开关。

advanced 的 txt 和 ocr 都能开启图片分析。txt 只过滤正文等类型的视觉模型抽取，不禁止图片区域分析。服务端全局禁用时，请求不能强行开启。

## 公式现状与设计影响

已提交版本没有公开 formula_enable。已有公式路径不能仅通过停止本地公式模型来全部关闭：

| 等级与模式 | 已提交版本的公式处理 |
| --- | --- |
| flash/txt | 原生提取，不走质量等级的公式专用识别流程 |
| flash/ocr | 本地 OCR 路径，没有调用质量等级的本地公式识别流程 |
| basic/txt、basic/ocr | 本地公式识别模型处理行内、独立公式；表内内容另受表格归属处理影响 |
| standard/txt、advanced/txt | 本地公式模型处理最终表格外的行内公式；独立公式由视觉模型处理 |
| standard/ocr、advanced/ocr | 不调用该本地公式识别模型，但视觉模型仍可识别公式 |

因此，“没有调用本地公式模型”不等于“没有公式结果”。

工作区的公式开关候选实现采用以下语义：false 跳过本地公式识别及视觉模型的独立公式抽取；独立公式最终改为图片；行内公式不再遮罩，交给原生文字或普通文字识别。该语义保留内容，但不保证复杂公式的文本准确率。

表格解析和图片分析保持各自独立。formula_enable=false 不能保证整份产物完全没有数学表达或 LaTeX：表格模型、图片解释和普通正文提取仍可能产生数学内容。若需要“任何路径都不得生成公式表达”，这是更强的需求，不能由该候选开关直接保证。

## 非 PDF 原生格式

Office、HTML、CSV 等进入独立原生解析分支，PDF 的 parse_mode 和 image_analysis 不传入这些分析器。原生 Excel 不能通过 ocr_mode=ocr 自动变为视觉模型解析。table_enable=false 被明确拒绝。公式开关若沿用当前候选边界，也应明确拒绝关闭，避免接受参数却无效果。

## 验证边界与后续验收

以上是源码路径结论，不是所有组合的模型质量结论。此前部署验收覆盖 advanced、auto 的表格和图片开关，以及原生 Excel；没有覆盖全部等级、OCR 模式或公式开关。

完成公式方案后，basic、standard、advanced 各有 3 种 OCR 配置和 8 种开关组合，共 72 组配置。auto 至少使用文本 PDF 和扫描 PDF 两类输入，另加混合 PDF、图片、表内公式、图片内公式和布局漏检样本。flash 和原生格式另测参数拒绝边界。检查正文完整性、表格结构、公式文本、截图、图片解释及实际模型调用，不能只检查任务 completed。

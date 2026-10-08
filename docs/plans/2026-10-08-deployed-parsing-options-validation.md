# 已部署服务的解析开关验证

本次验证直接调用 `http://192.168.20.28:8000`。没有修改服务配置或生产代码。验证目标是确认 `table_enable` 和 `image_analysis` 能否分别开启和关闭。

## 当前结论与边界

受控 PDF 的四种开关组合均已通过。表格关闭后保留截图，不输出表格结构化文本。图片分析关闭后保留流程图截图，不输出流程图解释。

用户提供的 `2062.xlsx` 已完成四种组合验证。Excel 走原生解析路径，实际输出标记为 `tier=flash`、`parse_mode=txt`。该路径不支持关闭表格解析。图像分析开关两种取值的输出完全相同。因此，不能将受控 PDF 的开关结论推广到原生 Excel。

## 服务与样本

- 健康接口返回 `status=ok`、`version=4.0.10`。
- OpenAPI 包含 `table_enable` 和 `image_analysis`，字段说明与本分支实现一致。
- `/v1/tiers` 提供 flash、basic、standard、advanced。
- 本次使用 advanced，服务公布模型为 `MinerU2.5-Pro-2605-1.2B`。
- 没有服务端提交号接口证据。因此，只确认版本字符串、接口字段和实际行为，不将版本字符串等同于源码提交证明。
- 样本为本次生成的一页 PDF，包含一个三列表格、一个三节点流程图、表题、表注和两段独立正文。
- 样本 SHA-256：`7da292fc85aa03f8105270a40ef7c37f8d892f773367e9f6d7f910a12665c0a2`。
- 请求使用 inline 来源、`tier=advanced`、`ocr_mode=auto`。产物包括 Markdown、Middle JSON、Structured Content 和 ZIP。
- 四个任务于服务端记录的 `2026-10-08T05:40Z` 时段完成。本次使用真实部署的模型，没有替换推理响应。

## 四种组合

| table_enable | image_analysis | 表格块 | 图片块 | 流程图解释 | 任务终态 |
| --- | --- | ---: | ---: | --- | --- |
| true | true | 1 | 1 | 有，输出 Mermaid | completed |
| true | false | 1 | 1 | 无，图片正文为空 | completed |
| false | true | 0 | 2 | 有；原表格图片正文为空 | completed |
| false | false | 0 | 2 | 无，两张图片正文均为空 | completed |

Mermaid 是用文本描述图形的格式。本样本开启图片分析时，输出的节点为 Receive order、Check stock、Ship goods，箭头方向与原图一致。

开启表格时，输出包含 Q1/Q2/Q3 和 101/202/303 等单元格值。关闭表格时，这些值不进入 Markdown 正文。即使图片分析同时开启，也没有重新解释原表格区域。

四种组合均保留表题、表注、两段独立正文和流程图题注。ZIP 均包含两张 JPEG。已实际解码图片，比较 Structured Content 的内嵌图片与 ZIP 图片哈希，并查看两张裁图。

| 区域 | 坐标 | 图片大小 | SHA-256 |
| --- | --- | --- | --- |
| 表格 | `[0.069, 0.175, 0.915, 0.361]` | 1459 × 425 | `29e27a92c6344846b227cd8c66cf41136c4f53379bf29b782d0611266de9dad5` |
| 流程图 | `[0.085, 0.517, 0.903, 0.613]` | 1410 × 220 | `169b024515a8e3c8912a44234e6cdda4a3ccfbf266a424898b4c98ccab2f3e77` |

四种组合的截图坐标、大小和哈希相同。截图保留行为不受图片分析开关影响。独立下载的 Markdown 和 Structured Content 使用 data URI 内嵌图片；ZIP 还提供独立图片文件，不能把 data URI 当作 ZIP 文件路径。

## 可复查任务

| 组合 | job_id |
| --- | --- |
| true / true | `job_bda1a6ad25d4d1884a71bdea` |
| true / false | `job_6768b16a28b080f22ef44b78` |
| false / true | `job_9b53e0528607282b5b949b14` |
| false / false | `job_c19e3a91c95688b83c471e0b` |

本地证据保存在仓库忽略目录 `.tools/deployed-options-20261008/controlled/`。每种组合均保存请求、任务响应、四类产物和裁图。`summary.json` 保存原始结果摘要；`assertions.json` 保存四种组合的通过记录。

脚本 `.tools/verify_deployed_options.py` 提交任务并轮询至终态。已保存 job_id 的组合会复用原任务，不会因为重复运行而重新提交。脚本 `.tools/assert_deployed_options.py` 检查正文、题注、表格文本、图片解释、图片解码及图片哈希。

## 附件 2062.xlsx 的实际结果

- 原文件：`D:/BaiduSyncdisk/cowork/行业知识图谱智能体/doc/2062.xlsx`。
- 大小：3,100,764 字节。SHA-256：`64630215137d3712ef3549f86641ea3a944c07828f7c8e20065ff73576c0a1b2`。
- 工作簿包含 10 个工作表、90 个公式和 30 个媒体文件。没有 OOXML 原生图表部件。媒体文件数与解析图片块数不是同一指标，不能直接比较为完整率。
- 文件超过服务的 1 MiB inline 上限。首次 inline 请求被来源校验拒绝，不能用于判断开关。随后通过上传接口传送原文件，得到 `file-9ad18352c4591a4afd75d5ff`，再使用 file_id 完成以下矩阵。
- 请求均指定 `tier=advanced`。成功产物中的实际解析标记均为 `tier=flash`、`parse_mode=txt`。这表明 Excel 使用原生解析路径，并未进入 advanced 的图片语义分析路径。

| table_enable | image_analysis | HTTP / 任务结果 | 表格块 | 图片块 |
| --- | --- | --- | ---: | ---: |
| true | true | 202 / completed | 10 | 26 |
| true | false | 202 / completed | 10 | 26 |
| false | true | 400 / parsing_option_unsupported | 不适用 | 不适用 |
| false | false | 400 / parsing_option_unsupported | 不适用 | 不适用 |

成功的两个任务还各有 10 个标题块和 7 个公式块。其 job_id 分别为 `job_6f97b4be14d52073b571ede8` 和 `job_cf7493f85045bcf8d76345d2`。

关闭表格的两种请求均在提交阶段返回 HTTP 400，错误参数为 `table_enable`，没有创建解析任务。错误消息为 `table_enable=False is not supported for '2062.xlsx' with tier 'advanced'`。该结果符合当前接口对原生 Excel 的限制，不能报告为 Excel 表格开关验收通过。

开启和关闭图片分析时，Markdown、Middle JSON 和 Structured Content 均逐字节相同。下表记录对应产物的 SHA-256。

| 产物 | SHA-256 |
| --- | --- |
| Markdown | `f07d560228e5b3468e76337bb095fc186614c5a91aed1b0273200252648a20ee` |
| Middle JSON | `6012011866bc850cafea8661e521a0dd30b72fa199db8aa15573213be1e15965` |
| Structured Content | `8978fde4cf24f5359ba7bcbd4325227cf763827dbd72a114f52233b57fd6f7c0` |

因此，该附件证明图片分析参数可以被接口接受，但不能证明其在 Excel 路径上产生开关效果。结合实际解析标记，结果与原生 Excel 不执行 advanced 图片语义分析的约定一致。

本次没有修改或转换原工作簿。验证后原文件 SHA-256 与验证前一致。没有逐单元格检查内容完整性、公式正确性或图片内容归属。上述块数量不能作为工作簿内容准确率。

本地证据位于 `.tools/deployed-options-20261008/attachment-2062-upload/`，包括上传记录、请求、任务响应、产物、`summary.json` 和 `output-comparison.json`。工作簿结构记录位于 `.tools/deployed-options-20261008/attachment-2062/workbook-source.json`。

本次没有执行 Linux 单元回归、全格式验收或生产放量；这些结论不由上述任务推导。

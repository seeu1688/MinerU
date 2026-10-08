# 请求级解析开关设计

日期：2026-10-03

2026-10-08 迭代补充：用户授权将 `formula_enable` 纳入同一 PR。该字段默认 true，只接受布尔值；false 停止本地公式专用识别和视觉模型的独立公式抽取。独立公式保留截图；行内公式使用普通文字提取。仅支持 basic、standard、advanced 的 PDF/图片，Flash 和原生格式明确拒绝关闭。表格和图片解释仍由各自开关控制，不能承诺整份产物没有数学表达。详细实现和验收边界见[公式迭代说明](2026-10-08-formula-options-validation.md)。下文保留首版设计背景，涉及“不增加公式开关”的首版范围由本段替代。

修订日期：2026-10-06（落实评审建议，完成本地实现与验证）

目标分支：`feat/api-parsing-options`

核对基线：`ed50cc15bc2c9bfb00520dadfe61979866e62236`，源码版本 `4.0.10`
状态：本地实现和自动化验证完成，真实 basic 样本已验收。Linux 回归和 standard/advanced 模型质量待验收。具体结果见[验证报告](2026-10-06-api-parsing-options-validation.md)。用户已授权完成实现、验证、运维文档及 PR。

## 1. 需求与范围

截图反馈希望保留 tier 的简化入口，同时让开发者决定是否解析表格、是否执行图片/图表语义分析，避免复杂表格和流程图被不合适的模型输出替代。

本设计对应当前仓库的 `POST /v1/parse/jobs`、远程 Python SDK 和本地 Python SDK。截图里的 `mineru_table_enable`、`mineru_image_analysis` 作为需求名称；建议公开参数沿用仓库命名风格，使用 `table_enable`、`image_analysis`。不据截图推定官方线上接口已支持这些字段，也不将软件 4.x 与历史 HTTP `/api/v4/` 混为一谈。

首版只增加这两个开关。不恢复旧参数集合，不增加公式开关、逐页/逐文件覆盖或自定义 backend/effort。Doclib、其 CLI/缓存和 Gradio 的新交互不纳入首版；原有调用保持默认行为。

评审修订补充接口历史、严格布尔校验、表格方向和原生表格回填条件。实施阶段继续按依赖实测修订。

两个开关解决不同问题。`table_enable` 控制表格结构识别。`image_analysis` 让同一服务的不同请求分别控制图片语义分析，主要用于 advanced 档的流程图等输入。服务启动时的全局开关不能替代请求级控制。因此，本设计保留两个开关。后续可以分两次提交，但不能将只实现表格开关视为全部需求完成。

## 2. 已核对的现状

| 位置 | 源码事实 | 对设计的影响 |
| --- | --- | --- |
| `mineru/parser/api_server.py:CreateJobRequest` | 当前只有 files、tier、ocr_mode、output_formats、callback；请求模型禁止多余字段 | 需要正式修改请求契约，客户端单独加字段无法生效 |
| 同文件 `create_job`、`_run_job`、`create_app` | 图片分析取自 app.state.image_analysis，创建应用默认 True；任务再传给 parse_async | 将请求值解析为任务独立配置；不能修改 app.state |
| `mineru/parser/api_client.py:MinerUApiParser`、`_build_payload` | 客户端没有两个开关 | 增加显式类型参数；未指定时省略字段 |
| `mineru/parser/__init__.py`、`mineru_parser.py`、`backend/analyze.py` | 本地同步/异步入口已有 image_analysis=True | 复用其语义，新增 table_enable，并补齐所有分支透传 |
| `mineru/parser/tier.py` | flash/basic/standard/advanced 对应 flash/medium/high/xhigh | 不改变 tier 映射 |
| `backend/analysis/pdf/window.py:_inference_options` | 仅 xhigh 将 image_analysis 传给 VLM，其余档位强制 False | True 只允许已有图片分析能力，不自动升级档位 |
| 同文件 `_prepare_pdf_window`、`_process_text_and_formulas` | basic/standard TXT 有原生表格优先路径；basic 有本地表格识别 | 不能只屏蔽一次 VLM 表格调用 |
| 同文件 `process_pdf_windows` | Flash TXT 直接调用 DocVortex PdfModel.predict | 首版不承诺关闭此独立原生引擎的表格抽取 |
| `model/vlm/contracts.py`、`async_runtime.py` | 已声明/透传 not_extract_list 与 image_analysis | 可作为表格关闭的候选接入点，仍需验证依赖实际行为 |
| `tests/unittest/test_parser_api_contract.py` | 明确断言客户端不含 image_analysis，且旧 table_enable 全局选项已移除 | 本方案改变既有公开契约；审核通过后才能修改对应断言，不恢复旧环境变量读取 |

源码证据不等于模型质量验收。实施环境已安装 `mineru-vl-utils 2.0.5` 和 `DocVortex 0.5.9`。同步/异步的四项依赖契约测试已通过。测试使用真实依赖处理布局和抽取调度，仅替换模型预测，因此不证明真实模型的识别质量。

依赖核对发现：只传 `not_extract_list=["table"]` 时，表内图片仍可能进入图片分析。advanced 关闭表格时，必须先通过公开布局接口取得区域，再排除完整位于表内的内容块，最后调用外部布局抽取接口。保持常驻异步运行时的并发限制和取消语义。表格开启时仍使用原有两阶段接口。

### 2.1 接口历史与上游提案

本地 Git 历史确认：2026-07-07 的提交 `642ba0b177ea8cfa6bfb25dc5a2d9793a011c751`，标题为 `feat: remove legacy formula and table options from CLI and API`，主动移除了旧表格和公式选项。改动包括服务端启动参数、CLI 参数和环境变量读取。这说明本方案涉及既有接口决策，不能只当作参数透传修复。

同一提交还做了两项改动：

- 新增 `_discard_legacy_formula_table_kwargs`，丢弃传入的旧参数。该函数不是删除前就存在的证据。
- 删除 medium 路径的 `_is_medium_table_enabled` 和对应的提前返回条件。删除前源码有本地表格识别的开关分支，但本轮没有运行历史版本。

因此，不能从这次提交推出“表格开关在全部 VLM 路径上从来没有生效”。它也不能证明当前 `not_extract_list` 满足本设计。当前依赖仍需单独验证。

本方案与旧接口的区别是：HTTP 使用任务级选项；本地 SDK 使用显式参数；不恢复全局表格环境变量和启动参数；明确规定关闭后的截图输出，并验证实际跳过识别。

若目标是提交上游，建议先用本设计说明上述区别。可以通过 Issue、Discussion 或 PR 说明沟通。截图中的“直接提 PR”表示可以提交提案，但不表示维护者已接受具体契约。无需强制另开 Issue，也不能仅凭删除历史判断 PR 必然被拒绝。若仅用于自有分支，上游接受与否不构成本地实施条件；技术验证仍然必须完成。本轮未查询线上讨论，也不发送任何外部消息。

## 3. 建议的公开契约

HTTP 请求顶层增加任务级字段，同一任务内文件共用：

| 参数 | HTTP 类型与默认 | 语义 |
| --- | --- | --- |
| `table_enable` | 严格布尔值，省略为 True；null 非法 | True 使用现有表格流程；False 在支持路径停止表格结构/内容抽取并保留区域截图 |
| `image_analysis` | 严格布尔值或 null，省略/null 继承服务配置 | False 停止图片/图表语义分析；True 允许当前档位原有能力；不控制素材导出 |

拒绝字符串 `"false"`、数字 `0/1` 等隐式类型转换；使用现有 API 错误封装及参数校验 HTTP 400 约定。HTTP 未知字段继续禁止。

请求模型使用 Pydantic 的 `StrictBool`。这是只接受布尔值的校验类型。待实现声明如下：

```python
from pydantic import StrictBool

table_enable: StrictBool = True
image_analysis: StrictBool | None = None
```

这两行属于 `CreateJobRequest` 的字段声明。普通 Python SDK 的类型注解不执行运行时校验。SDK 入口也需显式检查布尔类型；远程 SDK 另外允许 None。非法值应在上传文件或调用模型前报错。

远程 `MinerUApiParser` 两个构造参数均为 `bool | None = None`；None 表示不发送字段。尤其不能通过 `if value` 判断是否发送，否则 False 会丢失。本地 SDK 新增 `table_enable: bool = True`，已有 `image_analysis: bool = True` 保持不变；本地不引入服务端继承语义。新增参数不挤占既有可位置调用参数的位置，公开签名保持完整类型注解。

图片分析的服务端策略建议保留现有禁用能力：

1. 请求省略/null：继承 `create_app(image_analysis=...)`。
2. 请求 False：关闭。
3. 请求 True 且服务允许：开启允许值，由 tier 决定实际是否使用。
4. 请求 True 但服务禁用：明确返回 HTTP 400，参数 `image_analysis`，不静默忽略、不重新开启。

第 4 项是本设计的建议政策，并非现有源码已实现的限制；人工审核需确认。首版不新增服务端表格禁用参数或环境变量。

示例（待实现接口）：

```json
{
  "files": [{"source": {"type": "file_id", "file_id": "file_example"}}],
  "tier": "advanced",
  "ocr_mode": "auto",
  "table_enable": false,
  "image_analysis": false,
  "output_formats": ["markdown", "middle_json", "zip"]
}
```

## 4. 关闭后的输出与支持边界

`table_enable=false` 的目标是停止结构识别，并保存已检测表格的原始区域，不是删除表格或承诺恢复为正确的普通文本。

- 保留页码、区域位置、阅读顺序和截图；结构输出使用现有 image/视觉容器协议，Markdown 输出图片引用，不生成伪造的空表格或 HTML 单元格。
- 表题、表注必须保留，并按共享协议合法地关联/排列；区域内部已归属于表格的文字和公式不得重复流入正文。
- 不关闭整页布局检测。开关只能控制已检测的表格区域，不承诺修复模型漏检或错分的表格。
- 图片分析关闭后仍提取/导出图片素材。它不等于客户端 `include_images`，也不关闭页面 OCR、表题或图注文本识别。
- 表格关闭、图片分析开启时，其他图片可正常分析；被禁用的表格不能通过“转换为图片”又被送入图表分析。转换必须放在语义抽取之后，且结构抽取需事先屏蔽。

表格截图的方向统一按页面渲染结果保留，不额外将表格内容转正。页面自身的旋转按现有渲染流程处理。basic/standard 在表格关闭时跳过表格专用方向检测。advanced 本来就不经过该检测分支；不为它新增方向模型，也不假设 VLM 会提供转正角度。裁图和布局坐标必须使用同一坐标系。90°、180°、270° 表格需分别验证，不能发生二次旋转、裁切错位或内容缺失。

首版建议矩阵：

| 实际执行路径 | table_enable=False | image_analysis |
| --- | --- | --- |
| PDF/图片，basic | 支持：跳过原生优先和本地表格识别，保留区域 | 当前无图片语义分析；True 不增加能力 |
| PDF/图片，standard | 支持：跳过原生优先及 VLM 表格抽取，保留区域 | 同上 |
| PDF/图片，advanced | 支持：VLM 表格布局保留、内容抽取跳过，再保存截图 | True/False 控制现有 VLM 图片分析 |
| Flash PDF/图片 | 首版明确不支持，False 报错 | 沿用无图片语义分析的行为 |
| Office/HTML/EPUB/OFD/CSV/TSV 等原生路径 | 首版明确不支持，False 报错，不强制转 PDF | 不改变原生解析，False 不删除原有图片内容 |

True/省略 table_enable 不产生上述限制，保持现状。矩阵按实际文件路由判定，不能仅看请求 tier：原生输入可能被归一为 flash。若人工要求 Flash 和 Office 也必须支持关闭，则应扩展为单独的 DocVortex 公开接口设计，不能从 MinerU 导入其私有实现或仅删掉解析后结果冒充“跳过识别”。

不支持的组合在源类型已可靠确定时于入队前返回 HTTP 400；URL 等提交时无法可靠确定类型的输入，在文件解析前返回明确的文件级错误，沿用现有 partial/failed 状态。建议专用错误码 `parsing_option_unsupported`，含字段名、文件和实际路径，不静默成功。

## 5. 实现方法与顺序

### A. 先验证 VLM 跳过能力（实施门槛）

对部署使用的 mineru-vl-utils 版本做最小实验：验证 `batch_extract_with_layout` 跳过 table 时保留区域框和顺序，并且不调度表格内容抽取。advanced 使用 `batch_layout_detect` 后再执行该抽取接口，以便在两阶段之间排除表内图片。同步与异步均核对。还需验证无表格页面、其他图片分析、运行时并发和取消。

若任一路径不成立，先补公开适配能力并收窄依赖版本，或提交修订设计供审核；不以“抽取后清空 HTML”冒充推理开关，也不全局修改共享 predictor。源码接口存在只证明可传参，不能替代此验证。

### B. 请求、SDK 与任务隔离

1. CreateJobRequest 增加上述字段；在创建任务时解析服务端图片策略，冻结本次任务配置。
2. `_run_job` 每个文件路由后校验能力，再以显式命名参数传入 parse_async。
3. 两个 SDK 和 doc_analyze/aio_doc_analyze、PDF pipeline/window 同步补齐参数。仅两个字段，优先显式参数，无需新增通用插件配置框架。
4. 不修改 app.state、全局 config、共享模型单例配置或 NOT_EXTRACT_TYPES 常量；两种相反开关的并发任务必须独立。
5. 首版不扩展 Job 响应、MiddleJson 或 MinerUMetadata 协议；任务配置及实际路径写入内部记录/结构化日志。当前 MinerUMetadata 禁止额外字段，不能直接塞入开关值。

### C. 表格分阶段控制

1. 准备阶段：False 时跳过表格专用方向识别及 `_apply_native_txt_table_priority`，保留检测区域及其坐标；截图方向按第 4 节执行。常规文字/公式准备保留。standard TXT 同时跳过 `_split_native_high_table_blocks`，保持 `accepted_native_tables` 为空；完成阶段也跳过 `_restore_native_high_table_blocks`。不能只跳过原生识别，却保留原生表格拆分和恢复分支。
2. 推理阶段：`_inference_options` 为每次调用新建过滤集合，合并 TXT 原有过滤与 table，转换为 predictor 约定的 list；不得覆盖既有 TXT 过滤。advanced 关闭表格时先执行布局检测，再执行区域筛选和外部布局抽取。只有完整位于表格框内的正文、公式、图片等内容块才被筛除；保留表题、表注和部分交叠的相邻块。保持 image_analysis 独立。
3. 回填阶段：False 时跳过 `_apply_medium_table_recognition`。在正文/公式回填前保留区域归属信息，确保表内文字、公式不会重复输出；不得按简单矩形重叠删除相邻正文。
4. 视觉输出阶段：抽取结束后将被禁用的表格转为合法视觉容器，复用现有裁图和共享后处理能力；保留标题/注释和顺序。新增的小型显式辅助函数集中处理此转换。
5. 同步、原生异步、异步线程回退共用控制逻辑，保留当前 PDFium 锁、取消处理、页范围映射及资源释放顺序。
6. 下游确定性处理和 LLM 表格合并不得恢复被关闭的结构；使用合法图片表示并通过回归验证，无需修改全局 LLM 配置。

### D. 文档与旧契约

更新 `docs/next/api/parse-jobs.md`、`docs/next/sdk/api-parser.md` 及关联本地 SDK 文档，补充示例、默认值、支持矩阵、错误与迁移说明；核对中英文 usage 文档避免矛盾。只说明本仓库实现，官方远程服务是否接受新参数必须另行核验。老服务拒绝新参数时客户端原样报告，不自动去掉 False 重试。

CLI/Doclib 不暴露新开关；未来若扩展，必须先将解析选项纳入缓存/任务去重身份，避免同文档同 tier 返回相反配置的旧结果。

## 6. 验收计划

| 类别 | 必须验证的行为 |
| --- | --- |
| 兼容 | 老请求不带字段时 payload、路由和结果保持原样；不恢复旧环境变量影响 |
| 参数契约 | True/False/省略/null 按约定处理；拒绝字符串、整数、未知字段；SDK False 确实发送 |
| 服务策略 | 图片继承、请求关闭、服务禁用时请求开启四种情况；明确错误 |
| 全链路 | 本地/远程 SDK，同步/异步/线程回退和 HTTP job 参数准确到达实际执行点 |
| 表格控制 | basic TXT/OCR，standard TXT/OCR，advanced TXT/OCR；被关闭路径的识别器调用次数为零；默认路径不变 |
| 组合与并发 | 两开关四种组合；关闭表格不会被图片分析重新处理；相反配置并发无串扰 |
| 输出完整性 | 表格截图真实存在且可随产物下载；标题、注释、邻近正文保留；无重复表内内容；无无效空表 |
| 边界 | 页范围和坏页映射、多页表格、无表格页；basic/standard/advanced 的 90°、180°、270° 表格截图方向和裁切；原生文件归一化及不支持路径明确失败 |
| 原生表格回填 | standard TXT 关闭表格时不执行原生优先、拆分或恢复；不会重新插入已识别表格 |
| 依赖与质量 | 对实际 VLM 依赖做集成验证；人工对照复杂表格、流程图、混合页面的原图和结果 |

主要复用 `test_parser_api_contract.py`、`test_parser_api_ocr.py`、`test_native_pdf_table_pipeline.py`、`test_pdf_mfr_table_routing.py`、`test_pdf_analyze_visual_blocks.py` 及现有异步窗口测试。只替换与新契约直接冲突的断言，保留其它旧参数拒绝测试。

单元测试通过仅证明控制链和输出约束。模型实测与原图对照完成后，才能报告实际样本验收完成。最终验证报告必须分别记录自动化测试、依赖契约测试和真实模型样本验证，不能互相替代。

## 7. 人工审核决策

建议确认以下五项后再实施：

1. 参数采用 `table_enable` 与 `image_analysis`，均为任务级；保留 tier 与现有默认行为。
2. 表格关闭采用“停止结构识别、保留截图”，接受不提供表内结构化文本；图片关闭只停止语义分析。
3. 首版表格开关覆盖 basic/standard/advanced PDF 与图片；Flash/原生格式明确报不支持。如需全格式覆盖，扩大依赖侧设计范围。
4. 保留服务端禁用图片分析的上限，冲突请求报错；以 VLM 跳过行为实验证明为实施门槛。
5. 接受这是对既有接口决策的调整。保留两个开关的完整需求；若提交上游，在提案中说明与旧全局开关的区别。表格关闭后的截图按页面渲染方向保留，不额外转正。

用户已授权在当前分支完成此次 PR。以上审核点作为实施和验收依据；技术验证不因授权而省略。

# PR 审核说明

## 2026-10-08 公式迭代

本次在同一 PR #5620 增加第三个请求级开关 `formula_enable`。默认 true。false 停止公式专用识别，独立公式转为截图，行内公式使用普通文字提取。支持 basic、standard、advanced 的 PDF/图片；Flash 和原生格式明确拒绝关闭。图片和表格解释仍受各自开关控制。

专项测试同时检查模型不调用和最终结果转换，不只检查参数接受。实现、测试结果和未覆盖边界见[公式开关迭代与验证](2026-10-08-formula-options-validation.md)。旧版部署的 PDF 四种组合结果见[部署验收](2026-10-08-deployed-parsing-options-validation.md)，不能当作新增公式开关的部署证据。

下文是首版交付记录。原 PR 当前已不是草稿；2026-10-08 更新前读取的 CLA 检查为 SUCCESS。后续提交的检查状态以 GitHub 最新结果为准。

## 首版记录

本次修改在解析 API 和 Python SDK 增加两个请求级开关。调用方可以停止表格结构抽取，也可以停止模型解释图片或图表。省略开关时保持原有默认行为。

提交记录：代码提交 `ff811484fc8f418c2bdcb113298f0023c43b3af1`，分支已推送至 `seeu1688/MinerU`。上游草稿 PR 为 [#5620](https://github.com/opendatalab/MinerU/pull/5620)，目标分支为 master。

2026-10-06 创建后，GitHub 显示无合并冲突。创建初期 CLA 检查曾要求贡献者签署许可协议，该失败不属于代码测试失败。2026-10-08 更新前重新读取 PR，CLA 已为 SUCCESS，PR 已不是草稿；新提交后的状态需重新检查。

## 接口与行为

- HTTP `table_enable` 默认为 true。false 仅支持 basic、standard、advanced 的 PDF 和图片。检测到的表格保留为区域图片；表题、表注和相邻正文保留。
- HTTP `image_analysis` 默认为 null，继承服务配置。false 保留图片素材和正文 OCR。服务禁用图片分析时，显式 true 返回 HTTP 400。图片语义分析仅在 advanced 档执行，不自动提升 tier。
- HTTP 使用严格布尔值，拒绝字符串和整数。远程 SDK 用 None 省略字段，并原样发送 False。本地 SDK 两个参数只接受 bool。
- Flash 和原生格式不能关闭表格。已知类型在任务创建前拒绝；URL 下载后按实际文件类型返回文件级错误。

## 实现重点

请求参数依次经过远程 SDK、CreateJobRequest、任务执行、本地 SDK、统一分析入口和 PDF 窗口。每个任务保留自己的开关值，不修改应用或模型的默认配置。

basic 关闭本地表格识别和原生表格优先处理。standard 同时关闭原生表格拆分与回填。advanced 关闭表格时，先调用公开布局检测接口，再排除完整位于表格内的内容，最后调用公开外部布局抽取接口。这样可防止表格内部图片被图片分析重新处理。

表格类型保留到正文和公式归属处理结束。之后转为图片，再复用已有素材保存流程。部分交叠的邻近块不会被删除。截图保留页面渲染方向，不额外按表格角度转正。

不修改 DocVortex 的共享协议，不恢复旧环境变量，不新增 CLI 或 Doclib 开关。解析 metadata 仍只包含现有 tier 和 parse_mode。

## 验证

- 完整单元回归：2877 passed、23 failed、27 skipped。剩余 23 项在未修改基线全部复现；新增失败为 0。
- 独立 HTTP VLM 回归：39 passed。实际依赖测试和同步/异步关闭表格集成均通过。
- 真实 basic 模型：`demo1.pdf` 第 6 页的 2 个表格在关闭后转为 2 张图片，截图哈希相同；题注和正文保留。
- 真实 basic API 任务：两个开关的四种组合均 completed，下载 ZIP 均包含 2 张截图。
- Ruff 和补丁空白检查通过。

Linux 回归、standard/advanced 真实模型质量，以及复杂流程图和旋转表格样本仍待验收。当前证据不代表生产或官方云服务验收。建议以草稿 PR 提交，供维护者审核接口和范围。

## 审核材料

- [设计与需求取舍](2026-10-03-api-parsing-options-design.md)
- [验证报告与基线失败分类](2026-10-06-api-parsing-options-validation.md)
- [接口、升级、验收和回滚步骤](../next/api/parsing-options-operations.md)
- [HTTP 字段](../next/api/parse-jobs.md)
- [远程 SDK](../next/sdk/api-parser.md) 与[本地 SDK](../next/sdk/parser.md)

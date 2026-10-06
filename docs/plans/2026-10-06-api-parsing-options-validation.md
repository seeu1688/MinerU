# 解析开关验证报告

本次修改增加请求级 `table_enable` 和 `image_analysis`。修改覆盖 HTTP 任务、本地 SDK、远程 SDK、同步和异步 PDF 流程。目的是让调用方选择是否抽取表格、是否解释图片。

## 验证环境与结论

- 分支：`feat/api-parsing-options`。
- 已验证代码提交：`ff811484fc8f418c2bdcb113298f0023c43b3af1`。后续补充 PR 状态只修改文档。
- 基线：`ed50cc15bc2c9bfb00520dadfe61979866e62236`。2026-10-06 检查时，上游 master 仍是该提交。
- 系统：Windows；Python 3.13.7；CPU；本地小模型使用 ONNX。
- 主要依赖：DocVortex 0.5.9、mineru-vl-utils 2.0.5、pypdfium2 5.14.0、Pydantic 2.13.5。
- 验证日期：2026-10-06。

已确认请求参数传递、严格布尔值校验、任务配置隔离、表格区域保留、表格内部内容排除，以及同步和异步 HTTP 推理控制。真实 basic 模型完成一页 PDF 对照和 API 四种组合验收。

完整单元回归未全绿。本分支有 23 项失败，均在未修改基线出现。未观察到新增失败。Linux 回归和 standard/advanced 真实模型样本质量仍需验收。本报告不表示生产部署或官方云服务验证完成。

## 自动化验证

| 验证 | 结果 | 能证明什么 |
| --- | --- | --- |
| 本分支完整单元回归 | 2877 passed、23 failed、27 skipped；284.94 秒 | 本次功能及既有回归执行结果；不能表述为完整通过 |
| 未修改基线完整单元回归 | 2834 passed、24 failed、27 skipped；274.88 秒 | 同机、同依赖、UTF-8 下的失败对照 |
| 失败集合比较 | 本分支新增失败为 0 | 剩余失败未由本次提交新增；不代表已有失败可忽略 |
| 独立 HTTP VLM 回归 | 39 passed；36.43 秒 | 真实客户端和本机模拟推理服务的协议与控制链 |
| 新增关闭表格 HTTP 集成 | 4 passed | 同步/异步 × 图片分析开/关；保留裁图且不抽取表内图片 |
| 实际 VLM 依赖契约 | 4 passed，包含于完整回归 | 实际库跳过表格抽取并保留区域；仅替换模型预测 |
| 最终接口和架构复查 | 46 passed | OpenAPI 字段说明、严格布尔值、表格区域保留及依赖契约 |
| 最终格式改动复查 | 319 passed | PDF 输出、HTTP 契约及异步资源生命周期 |
| Ruff 与 Git 空白检查 | 通过 | 改动文件的代码规则和补丁空白检查 |

完整回归命令。Windows 使用项目虚拟环境，关闭仓库默认 coverage 输出，以独立目录保存临时文件：

```powershell
.venv/Scripts/python.exe -u -X utf8 -m pytest tests/unittest -o addopts='' -q --tb=short --basetemp=.tools/pytest-release
```

基线从 `git archive HEAD` 导出到隔离目录，再使用同一个虚拟环境执行相同测试。没有替换当前工作区的源文件。两个运行都执行所有单元测试，没有通过排除失败用例制造通过结果。

完整回归后，补充了 OpenAPI 字段说明及异步布局方法的中文说明，并按 Ruff 格式化改动文件。一个旧裁图测试替身补齐类型注解。这些修改不改变解析行为。最终 46 项接口和架构测试、319 项输出与异步测试均通过。22 个改动 Python 文件的 Ruff 检查和格式检查通过；文档本地链接检查通过。

### 剩余基线失败

以下失败全部在未修改基线复现。原因栏只列当前错误特征；未在本次 PR 中修改这些独立功能。

| 测试文件 | 数量 | 当前错误特征 |
| --- | ---: | --- |
| `test_cli_next_command_design.py` | 2 | 用户目录路径展开相关断言 |
| `test_doclib_cache_semantics.py` | 2 | Windows 创建符号链接权限不足，WinError 1314 |
| `test_doclib_config.py` | 6 | 路径分隔符及目录相关断言 |
| `test_doclib_instance_lock.py` | 1 | 子进程锁测试报 DoclibLockUnavailable |
| `test_kit_gradio.py` | 1 | 长文件名产物路径创建失败 |
| `test_kit_gradio_conversion.py` | 1 | 非生成器响应契约断言 |
| `test_kit_gradio_json.py` | 2 | 文件 CRLF 与字符串 LF 比较 |
| `test_kit_gradio_pdf_preview.py` | 1 | Windows 路径与素材清单路径比较 |
| `test_kit_gradio_source_preview.py` | 3 | HTML 预览的资源请求约束 |
| `test_mlx_server_native.py` | 3 | Windows 路径与 POSIX 路径比较 |
| `test_v1_router.py` | 1 | 托管进程命令构造断言 |

基线另有一个 `test_native_async_runtime.py` 路径断言失败。本分支用 `Path.resolve()` 比较同一个模型路径，消除路径分隔符差异。没有放松引擎构造、所属事件循环或唯一关闭断言。

## 真实 basic 模型对照

输入：仓库 `demo/pdfs/demo1.pdf`，只解析第 6 页。输入 SHA-256：

```text
f3b3be345bf2df8979f2491ca9466e078e4fd1d6a216611faa8566e4c44d474b
```

参数：`tier="basic"`、`ocr_mode="txt"`、`image_analysis=False`、`page_range="6"`。分别使用 `table_enable=False` 和 `True`。布局、OCR 检测和原生文本处理均使用实际实现；未替换模型预测。

| 输出 | 表格开启 | 表格关闭 |
| --- | ---: | ---: |
| structured content 表格块 | 2 | 0 |
| structured content 图片块 | 0 | 2 |
| 正文块 | 3 | 3 |
| 小标题块 | 2 | 2 |
| page_idx | 5 | 5 |
| 截图 | 2 | 2 |

两种状态的截图坐标和图片字节相同。关闭后图片正文为空，Markdown 不包含表内结构化文本。表题、表注、相邻正文仍存在。两张截图均已视觉检查。

| 截图 | 大小 | SHA-256 |
| --- | --- | --- |
| 上方表格 | 1274 × 369 | `3111348c57b8e83bc643895dd73402ce69c89fc96aa1198064b3ca56894479e9` |
| 下方表格 | 1274 × 370 | `cc2b17956f522cd92ca1783f04f09cac27e8ba9967be5e303d99d9d2025f172f` |

耗时分别为关闭 5.33 秒、开启 1.46 秒。关闭运行含首次初始化，不能用这两个数字推导性能增益或退化。

该样本是电子 PDF。它不证明扫描表格、复杂流程图、多页表格或旋转表格的真实模型效果。0/90/180/270 度只完成了自动化转换规则验证。

## 真实模型 API 任务与 ZIP 验收

使用 FastAPI TestClient 调用本分支服务应用。TestClient 在进程内执行 HTTP 应用；此次没有启动生产监听端口。请求使用实际 basic 模型和同一 PDF 第 6 页，产物请求为 `structured_content` 和 `zip`。

| table_enable | image_analysis | 任务终态 | 区域类型 | ZIP 图片数量 |
| --- | --- | --- | --- | ---: |
| false | false | completed | image | 2 |
| false | true | completed | image | 2 |
| true | false | completed | table | 2 |
| true | true | completed | table | 2 |

已检查实际任务终态、JSON 区域类型和下载 ZIP 内容。没有只用 HTTP 202 判断成功。basic 不执行图片语义分析，因此这些任务不能证明 advanced 图片分析的神经模型效果。

本地证据位于忽略目录 `.tools/acceptance/`。测试日志位于 `.tools/pytest-release.log`、`.tools/pytest-baseline.log`、`.tools/pytest-vlm-final.log` 和 `.tools/real-api-options.log`。模型权重、样本产物、临时环境和日志不进入 PR。上面的参数、计数和哈希写入本报告，供其他机器复验。

## 合并与发布前的验收

1. 在目标 Linux 环境执行完整单元回归，核对剩余失败。
2. 使用部署采用的 standard/advanced 模型，对扫描表格、流程图和混合页面执行两开关的四种组合。
3. 使用 90/180/270 度表格检查截图方向、边界、题注和相邻正文。布局漏检仍是模型质量问题，开关不补检测。
4. 并发提交相反参数，核对每个任务的 JSON、日志和 ZIP。单元测试已验证配置隔离；部署验收仍需检查实际服务配置。
5. 检查 Windows 或 Linux 目标机器的模型目录、写入权限和在途任务处理。按[运维说明](../next/api/parsing-options-operations.md)升级或回滚。

未完成上述验收前，可人工审核此 PR，但不能据此宣布生产放量完成。

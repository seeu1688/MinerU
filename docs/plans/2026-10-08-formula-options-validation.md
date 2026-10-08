# 公式开关迭代与验证

本次在原 PR #5620 中增加 `formula_enable`。目的是让调用方停止公式专用识别，并保留原始内容。没有改变 tier 的能力分工，没有增加 CLI、Gradio、Doclib 或环境变量开关。

## 接口与结果

- HTTP 默认 true；false 原样传递。HTTP null、字符串和数字非法。远程 SDK None 表示省略；本地 SDK 默认 true。
- basic、standard、advanced 的 PDF 和图片支持 false。Flash 和原生 Office、HTML、CSV 等格式明确返回 parsing_option_unsupported。URL 输入在下载确认类型后可能返回文件级错误。
- false 停止本地公式识别和视觉模型的独立公式抽取。独立公式在正文处理完成后转为图片，并复用素材保存流程。行内公式不再遮罩，由原生文字或普通文字识别处理；复杂公式文本准确率不保证。
- advanced 关闭公式时先检测布局，再过滤公式内部内容，最后按布局抽取。公式内部图片不单独送入图片分析。公式截图在图片分析完成后生成。
- 表格模型、原有图片解释和普通正文提取仍可能输出数学表达或 LaTeX；该开关不是全产物的数学表达过滤器。
- 三个开关互不覆盖。关闭表格时表内公式随表格截图保留，不作为独立公式再次识别。
- OCR 合法值为 auto、txt、ocr。auto 在文档级选择后两者之一。txt 不等于禁止全部 OCR。公式关闭逻辑覆盖 txt 和 ocr，同步和异步流程保持一致。

## 验证方法

公式专项覆盖严格布尔校验、HTTP 提交前拒绝、SDK 序列化、公式区域截图保留、本地公式模型不调用、行内文字不遮罩、安装版本的 VLM 库调度、三开关组合的同步异步窗口调度，以及最终结果的 equation 到 image 转换。

模型预测在这些自动化测试中被替换。测试证明参数传递、调用调度和结果转换，不证明数学识别质量。auto 的文档分类沿用原流程，专项矩阵针对分类后的 txt/ocr。

验证结果：公式专项 156 passed；包含专项、表格路由、HTTP 契约、OCR、资源生命周期、原生表格、正文回填、视觉素材和远程 VLM 的相关回归共 654 passed。9 个改动 Python 文件的 Ruff 规则检查及格式检查通过；补丁空白检查通过。

最终回归命令：

```powershell
.venv/Scripts/python.exe -m pytest tests/unittest/test_formula_options.py tests/unittest/test_parsing_options_vlm_dependency.py tests/unittest/test_pdf_mfr_table_routing.py tests/unittest/test_parser_api_contract.py tests/unittest/test_parser_api_ocr.py tests/unittest/test_pdf_memory_lifecycle.py tests/unittest/test_native_pdf_table_pipeline.py tests/unittest/test_pdf_analyze_block_content.py tests/unittest/test_pdf_analyze_visual_blocks.py tests/unittest/test_vlm_remote.py -q -p no:cacheprovider --no-cov
```

本次没有重新运行全仓库单元测试，没有部署候选服务，没有将旧版部署验收当作公式开关验收。真实模型、Linux 和业务附件质量仍待验收。

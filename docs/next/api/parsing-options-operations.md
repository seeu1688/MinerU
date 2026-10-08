# 解析开关运维说明

部署人员请先按[三个解析开关的本地部署手册](parsing-options-local-deployment.md)执行。手册固定功能提交 `0eb90d7d545ab497488bdd1a4b1e7bba57173d13`，包括安装、启动、接口检查、产物验收和回滚。

适用范围：本分支的 Local Parse Server、远程 Python SDK 和本地 Python SDK。本文不表示官方云服务已上线这些参数。验证结果见[首版验证报告](../../plans/2026-10-06-api-parsing-options-validation.md)和[公式迭代验证](../../plans/2026-10-08-formula-options-validation.md)。

## 改动与用途

`POST /v1/parse/jobs` 增加三个任务级开关。`table_enable` 控制表格结构和内容抽取。`formula_enable` 控制公式专用识别。`image_analysis` 控制图片语义分析，即由模型解释图片或图表的内容。不同请求可以使用不同开关，同一请求的所有文件共用开关。

省略三个字段时保持原有行为。不新增环境变量，不新增启动参数，不修改数据库结构。

## 参数规则

| 参数 | 默认规则 | 关闭后的结果 |
| --- | --- | --- |
| `table_enable` | HTTP 省略为 true；null 非法 | 已检测表格保留区域截图。不生成表格结构和表内文本。表题、表注、相邻正文保留。 |
| `image_analysis` | HTTP 省略或 null 继承服务配置 | 不解释图片内容。仍保存图片素材，不关闭正文 OCR。 |
| `formula_enable` | `true` | 停止公式专用识别。独立公式保留截图；行内公式使用普通文字提取，不保证复杂公式文本准确率。 |

HTTP 只接受真正的布尔值。`"false"`、`0`、`1` 都非法。远程 SDK 使用 `None` 表示省略字段。本地 SDK 三个参数只接受布尔值，默认均为 `True`。

`formula_enable=false` 与关闭表格的支持范围相同。它停止本地公式识别和视觉模型的独立公式抽取。独立公式在图片分析之后转为截图，不会因 `image_analysis=true` 再次被解释。表格模型、原有图片解释和普通文字提取仍可能输出数学表达或 LaTeX，因此该开关不保证整份产物完全没有数学表达。

OCR 模式是 `auto`、`txt`、`ocr`。`auto` 在文档级选择后两者之一。三个开关不会改变这个选择。`txt` 不是禁止全部 OCR，也不会自动关闭公式、表格或 advanced 的图片解释。

`table_enable=false` 仅支持 basic、standard、advanced 的 PDF 和图片。Flash 和原生 Office、HTML、CSV 等格式不支持。混合文件任务按实际文件类型判断；指定 advanced 不能将原生文件变成受支持的路径。

图片语义分析仅在 advanced 档具有实际作用。其他档位传 true 不会自动升级。若服务用 `--disable-image-analysis` 启动，请求不能用 true 重新启用；该请求返回 HTTP 400。

表格截图保留页面渲染方向。关闭表格后不额外将旋转表格转正。开关不修复布局漏检或误分类。只有明确归属于表格的内部内容被排除；部分交叠的相邻块保留。

## 升级步骤

1. 保存当前服务的版本号、启动命令和配置。保存正在处理任务的记录。
2. 在隔离环境安装审核后的提交。运行环境按模型后端选择基础安装、`.[torch]` 或 `.[full]`；需要运行开发测试时另装 `.[dev,test]`。不要将本次开发环境的全部依赖版本当作生产锁定文件。
3. 使用现有启动配置启动候选服务。保持原 tier、模型配置和鉴权方式。无需新增开关环境变量。
4. 先发送不带新字段的原有请求。确认解析和产物下载保持正常。
5. 用已上传的测试文件发送三个开关的八种组合。在 basic、standard、advanced 下分别覆盖 auto、txt、ocr。确认每个任务使用自己的配置。
6. 比较 Markdown、中间 JSON 和 ZIP 内的截图。检查表题、表注、相邻正文、页码以及旋转方向。不要只看 HTTP 202。
7. 检查 Flash、原生格式、非法类型及服务禁用冲突。确认错误可定位到字段。
8. 先升级服务端，再升级需要新开关的客户端。旧客户端省略字段，可以继续调用新服务。

HTTP 202 只表示任务已创建。必须轮询任务至 completed、partial 或 failed，再检查每个文件的结果。URL 输入在下载后才能确认实际类型；不支持的选项可能作为文件级错误返回。

## 调用示例

以下示例调用自行部署且已升级的服务。先通过 Files/Uploads API 取得 file_id，再替换示例值：

```json
{
  "files": [{"source": {"type": "file_id", "file_id": "file_example"}}],
  "tier": "advanced",
  "table_enable": false,
  "formula_enable": false,
  "image_analysis": false,
  "output_formats": ["markdown", "middle_json", "zip"]
}
```

远程 Python SDK：

```python
from mineru.parser import MinerUApiParser

parser = MinerUApiParser(
    api_url="http://127.0.0.1:8000",
    tier="advanced",
    table_enable=False,
    formula_enable=False,
    image_analysis=False,
    include_images=True,
)
result = parser.parse("sample.pdf")
```

本地 SDK：

```python
from mineru.parser import parse
from mineru.parser.writer import FileBasedDataWriter

def main():
    result = parse("sample.pdf", tier="basic", table_enable=False, formula_enable=False, image_analysis=False)
    result.save(FileBasedDataWriter("output/sample"))

if __name__ == "__main__":
    main()
```

异步入口为 `parse_async` 和 `MinerUApiParser.parse_async`，参数含义相同。仅下载 Markdown 不能确保同时取得所有图片文件；需要完整离线产物时下载 ZIP，或使用 SDK 保存结果。

Windows 本地脚本需保留示例的主入口保护。PDF 渲染会启动子进程；模块导入时直接执行解析会导致子进程启动失败。首次运行可能下载模型。生产环境应提前准备当前 tier 所需模型，并验证目录的读取权限。

## 错误处理

| 现象 | 处理方法 |
| --- | --- |
| HTTP 400，参数值非法 | 使用 JSON true/false，不使用字符串或数字。 |
| `parsing_option_unsupported` | 检查文件类型和实际 tier。原生格式或 Flash 应保留默认表格行为，或由调用方另行选择受支持的输入。 |
| image_analysis 被服务禁用 | 请求省略、null 或 false；如需开启，由运维修改服务启动配置。 |
| 旧服务拒绝新字段 | 升级服务端。不要自动删除 false 后重试，这会重新启用调用方要求关闭的行为。 |
| 截图缺失或图文重复 | 保留输入、请求参数、job_id 和完整产物，停止候选版本放量并检查布局与素材处理。 |

## 回滚步骤

1. 停止向候选版本分配新任务，等待或明确取消在途任务。
2. 将流量切回原服务版本，并恢复原启动配置。
3. 停止客户端发送新字段。需要保持关闭语义的请求应暂停处理，不得静默改为默认解析。
4. 保留失败任务及样本，记录回滚前后的提交号和依赖版本。

本改动没有数据库迁移。Doclib、CLI 和 Gradio 尚未增加这些开关；不要将其缓存结果当作开关验收结果。后续扩展 Doclib 时，解析选项必须进入缓存和去重身份。

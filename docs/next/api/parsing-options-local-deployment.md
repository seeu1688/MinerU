# 三个解析开关的本地部署手册

适用对象：运维人员。目标：将原 PR [#5620](https://github.com/opendatalab/MinerU/pull/5620) 的公式迭代部署到自行管理的 Parse Server。本手册不操作现有服务，也不表示候选版本已经部署。

## 版本与验收边界

- 仓库：`https://github.com/seeu1688/MinerU.git`。
- 分支：`feat/api-parsing-options`。
- 本次功能提交：`0eb90d7d545ab497488bdd1a4b1e7bba57173d13`。
- 三个参数：`table_enable`、`formula_enable`、`image_analysis`。软件版本字符串仍可能为 `4.0.10`；只看版本字符串不能判断是否包含本次功能。
- 相关自动化回归 654 项通过。公式专项 156 项包含在其中。模型预测在测试中被替换，不代表公式质量验收。Linux、真实模型和业务附件验收由部署现场完成。
- 之前 `192.168.20.28:8000` 的 PDF 验收只覆盖表格、图片开关；不能用它证明新增公式开关已部署。

PDF／图片的支持范围：

| 请求 tier | 关闭表格 | 关闭公式专用识别 | 图片语义分析 |
| --- | --- | --- | --- |
| flash | 不支持，报错 | 不支持，报错 | 不执行 |
| basic | 支持 | 支持 | 不执行 |
| standard | 支持 | 支持 | 不执行 |
| advanced | 支持 | 支持 | 可开关，受服务端全局配置约束 |

Excel、Word、HTML、CSV 等原生格式不支持关闭表格或公式。即使请求指定 advanced，也不能改成 PDF 的模型解析路径。

## 1. 保存当前服务信息

记录当前源码提交、Python 环境路径、完整启动命令、服务管理方式、监听端口、模型配置、模型目录、上传目录和鉴权方式。保存现有环境的依赖清单，例如在原环境运行：

```bash
python -m pip freeze > before-upgrade-requirements.txt
```

使用 uv 管理的环境也可执行 `uv pip freeze --python /实际环境/bin/python`。清单用于复查，不等同于适配所有硬件的部署锁文件。保留原环境用于回滚。

停止分配新任务后，等待在途任务结束。任务和文件引用不能仅凭上传目录存在就假定能跨进程恢复；切换前下载需要保留的产物，并记录 job_id。先在候选端口完成验收，不直接覆盖正在运行的环境。

## 2. 安装固定提交

下列命令在 Linux Bash 中执行。要求已安装 Git、uv，并有可用的 Python 3.12。目标目录应为新目录；已有目录时先核对用途，不覆盖现有生产目录。

```bash
git clone --branch feat/api-parsing-options https://github.com/seeu1688/MinerU.git MinerU-api-options-0eb90d7d
cd MinerU-api-options-0eb90d7d
git checkout --detach 0eb90d7d545ab497488bdd1a4b1e7bba57173d13
git rev-parse HEAD
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python .
source .venv/bin/activate
```

最后一条源码提交必须与本手册功能提交相同。使用后续提交时，先确认它包含该提交并重新验收。不要仅执行 `pip install mineru==4.0.10`，这不能保证安装本 PR。

基本安装包含 ONNX 和 llama.cpp 相关依赖。安装配置必须匹配原服务的模型后端；以下是可选配置，不要全部安装：

| 已选后端 | 在上述新环境中执行 |
| --- | --- |
| 本地小模型使用 Torch | `uv pip install --python .venv/bin/python ".[torch]"` |
| Linux 本地 VLM 使用 vLLM，或 Windows 本地 VLM 使用 LMDeploy | `uv pip install --python .venv/bin/python ".[full]"` |
| 远程 VLM，本地小模型使用 ONNX | 基本安装；仍需本地小模型文件 |
| 远程 VLM，本地小模型使用 Torch | 安装 `.[torch]`；无需仅为远程 VLM 安装本地 VLM 引擎 |

GPU 驱动、CUDA 和 Torch 构建应沿用现场已验证的组合。不要为三个开关随意更换模型或推理后端。模型默认首次使用时下载；离线部署须提前准备对应模型及依赖包。

Windows PowerShell 使用相同的 Git 命令；虚拟环境改为：

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe .
.venv/Scripts/Activate.ps1
```

Windows 安装可选依赖时，把表中 Python 路径改为 `.venv/Scripts/python.exe`。无法激活时可直接使用 `.venv/Scripts/mineru-kit.exe`，不必修改系统执行策略。

## 3. 核对代码和配置

在候选环境执行：

```bash
python -c "import mineru; from mineru.parser.api_server import CreateJobRequest; print(mineru.__file__); print({k: CreateJobRequest.model_fields[k].default for k in ('table_enable','formula_enable','image_analysis','ocr_mode')})"
mineru-kit api-server --help
```

模块路径必须指向候选环境安装的源码。参数默认值应为 table/formula `True`、image `None`、ocr `auto`。

复用现有 `MINERU_HOME`／`MINERU_CONFIG` 和模型连接配置时，先核对路径、权限和配置内容；不要覆盖原配置。配置默认路径为 `~/.mineru/config.yaml`，模型默认位于 `~/.mineru/models`。完整规则见[配置说明](../config.md)。三个请求开关不需要新增环境变量或启动参数。

## 4. 启动候选服务

先在服务器本机监听 `127.0.0.1:8001`，以下命令在前台运行。上传目录使用新的候选目录。启动 tier 只接受 flash、basic、standard；要允许 advanced 请求，使用 standard，并保留 advanced 能力。

复用现有本地 VLM 配置：

```bash
mineru-kit api-server --tier standard --host 127.0.0.1 --port 8001 --upload-dir ./candidate-uploads --preload-models --log-level info
```

若现有服务使用远程 VLM，改用以下示例，并替换上游地址；鉴权和模型名沿用现场配置：

```bash
mineru-kit api-server --tier standard --host 127.0.0.1 --port 8001 --upload-dir ./candidate-uploads --vlm-server-url http://127.0.0.1:30000/v1 --preload-models --log-level info
```

`--api-key` 用于调用方访问 Parse Server；`--vlm-api-key` 用于 Parse Server 访问上游 VLM，两者不同。已有鉴权服务必须保留鉴权配置。不要把示例端口直接当作现有上游地址。

要验证图片开关，启动命令不能包含 `--disable-image-analysis`；全局禁用时请求 true 会被拒绝。只部署 basic 时可用 `--tier basic`，但不能验收 standard／advanced。具体参数见[服务启动说明](../cli/mineru-kit-api-server.md)。

## 5. 检查服务字段

另开终端。Linux 使用 curl；Windows PowerShell 将 `curl` 改为 `curl.exe`。有鉴权时每条请求添加 `-H "Authorization: Bearer 实际密钥"`。

```bash
curl -fsS http://127.0.0.1:8001/v1/health
curl -fsS http://127.0.0.1:8001/v1/tiers
curl -fsS http://127.0.0.1:8001/openapi.json -o candidate-openapi.json
```

核对 health 为 ok、tiers 包含需要的等级，并在 OpenAPI 中确认三个字段和默认值。缺少 formula_enable 时停止切换，检查是否启动了旧环境。字段存在只证明接口已更新，下一步必须比较实际产物。

## 6. 验证开关实际效果

使用包含正文、表格、独立公式、行内公式和流程图的真实 PDF。先通过[上传接口](uploads-files.md)取得 file_id；默认 inline 上限为 1 MiB，大文件不能直接内嵌。不要把文件大小拒绝当作开关测试结果。

先发送不带三个开关的原有请求，验证兼容性。再把以下 JSON 保存为 `candidate-request.json`，替换 file_id：

```json
{
  "files": [{"source": {"type": "file_id", "file_id": "file_example"}}],
  "tier": "advanced",
  "ocr_mode": "auto",
  "table_enable": false,
  "formula_enable": false,
  "image_analysis": false,
  "output_formats": ["markdown", "middle_json", "structured_content", "zip"]
}
```

```bash
curl -fsS -H "Content-Type: application/json" --data-binary @candidate-request.json http://127.0.0.1:8001/v1/parse/jobs
curl -fsS http://127.0.0.1:8001/v1/parse/jobs/JOB_ID
curl -fsS http://127.0.0.1:8001/v1/files/OUTPUT_FILE_ID/content -o candidate-output.zip
```

第二条命令替换创建响应的 job_id，重复查询至 completed、partial、failed 或 canceled。第三条仅在 ZIP 产物存在时执行，替换 `files[].output_files.zip.file_id`。其他格式使用各自的 file_id 和文件后缀下载。检查每个文件的 status 和 error；partial 不能视为全部成功。

分别执行八种组合，顺序为 table／formula／image：TTT、TTF、TFT、TFF、FTT、FTF、FFT、FFF，T 为 true，F 为 false。每组使用相同样本和页范围，单独保存请求、job_id、任务响应和产物。

| 比较内容 | 必须检查的结果 |
| --- | --- |
| 关闭表格 | 检测到的表格转为截图，表格结构与表内正文不再抽取；表题、表注和相邻正文保留 |
| 关闭公式 | 独立公式转为截图，无专用公式识别文本；行内句子仍保留，不保证数学符号准确 |
| 关闭图片分析 | 图片素材保留，不生成图片语义解释；正文文字提取仍执行 |
| 关闭表格，同时开启公式／图片分析 | 表格内部内容不作为独立公式或图片重新解释 |
| 关闭公式，同时开启图片分析 | 独立公式截图不重新解释；表格和原有图片仍按自己的开关处理 |

在 basic、standard、advanced 下分别覆盖 auto、txt、ocr，共 72 组配置。auto 至少使用文本 PDF 和扫描 PDF；补充混合 PDF、图片、旋转表格、表内公式及真实复杂样本。图片没有可用文字层时，不把 txt 当作可靠扫描识别方案。basic／standard 的 image_analysis 两种值不应被当作有图片解释能力的证明。

另测 flash、Excel 等原生格式传 table/formula false，确认返回 parsing_option_unsupported；字符串 `"false"`、数字和 formula null 应返回参数错误。已知类型通常在任务创建前返回 HTTP 400；URL 输入可能在下载后以文件级错误返回。

关闭公式专用识别不保证整份文档完全没有数学表达：普通文字、开启的表格模型和原有图片解释仍可能输出公式。关闭区域也依赖布局检测；漏检或部分重叠须人工检查。

## 7. 切换与回滚

1. 运维保存验收样本、输出差异、功能提交、安装依赖清单及日志。业务人员确认内容质量后，再安排切换。
2. 使用现有 systemd、容器或其他管理方式，把启动路径改为候选环境；保留原鉴权、模型连接和需要的监听配置。确保旧进程已释放目标端口。
3. 切换后重新检查 health、tiers、OpenAPI，并执行一个三开关请求。健康检查不能替代产物检查。
4. 出现素材缺失、正文丢失、图文重复或任务错误时，停止分配新任务，处理在途任务，恢复原启动路径和配置。
5. 回滚到不支持 formula_enable 的版本后，客户端停止发送该字段；要求关闭公式的业务应暂停，不得删除 false 后静默重试。

本次没有数据库迁移。新增开关尚未接入 Doclib 缓存和 CLI／Gradio 控件。需要开关控制时调用 Parse API 或 Python SDK，不以旧缓存结果验收。完整语义见[开关运维说明](parsing-options-operations.md)，开发验证见[公式迭代报告](../../plans/2026-10-08-formula-options-validation.md)。

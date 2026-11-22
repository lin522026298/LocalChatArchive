# Local Chat Archive · QQ／微信 Agent 检索技能

一个 Windows 本地 Agent 技能：用自然语言查已归档的 QQ／微信聊天、查看上下文、取出有证据的附件。CLI 不打开聊天窗口，不占用前台或键鼠。

**它是检索层，不是归档工具，也不能只靠安装 QQ 或微信就读取聊天。** 查哪种平台就搭配哪种归档工具；两种都查则分别配置：

| 平台 | 需要先准备 | 技能使用的入口 |
| --- | --- | --- |
| QQ | [QQArchiveNext v1.0.0](https://github.com/lin522026298/QQArchiveNext/releases/tag/v1.0.0) 和已可查看的本地档案 | 便携版的 `QQArchiveCore.exe`，仅调用已发布的 `agent call` 读取操作 |
| 微信 | [CaptureNext v0.1.1](https://github.com/lin522026298/CaptureNext/releases/tag/v0.1.1) 和已归并的本地档案，另需对应 [CaptureNext 源码](https://github.com/lin522026298/CaptureNext/tree/v0.1.1) 及 Python 环境 | CaptureNext 自带的账号限定只读入口；不必重新编译桌面程序 |

同一档案可含多个账号。每次查消息必须指定账号，不把昵称或当前登录视为身份，不默认跨账号搜索。想查的是另一份安装或恢复档案，请另建配置文件。只读的是已归档的版本；未同步到本机、尚未归档、无法确认关联或旧客户端格式不会因使用 Agent 自动补齐。

## 安装

1. 按各归档工具自己的文档准备并确认已有档案可查看。只配置需要的平台即可。不必为查询再次启动采集器，不在技能里保存数据库密钥。
2. 安装 Windows Python 3.11 x64。在 PowerShell 中克隆此仓库，将 `local-chat-archive` 目录放入 Agent 的技能目录。Codex 默认位置示例（升级已有技能时保留原私有配置）：

```powershell
git clone https://github.com/lin522026298/LocalChatArchive.git
Set-Location LocalChatArchive
$skill = Join-Path $env:USERPROFILE '.codex/skills/local-chat-archive'
if (Test-Path -LiteralPath $skill) { throw '技能已存在；请先检查已有版本和私有配置' }
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $skill) | Out-Null
Copy-Item -LiteralPath (Resolve-Path './local-chat-archive').Path -Destination $skill -Recurse
Copy-Item -LiteralPath './examples/profile.example.json' -Destination (Join-Path $skill 'local.private.json')
```

3. 按 [示例配置](examples/profile.example.json) 编辑 `local.private.json`。QQ 的 `core` 指向公开程序包下 `backend/QQArchiveCore/QQArchiveCore.exe`（或你的安装中同名后台），`state` 是你打开的真实档案目录。微信的 `root` 指向包含 `archives/wechat-next` 的 **CaptureNext 安装根**，不是微信客户端路径；`source_dir` 和 `python` 分别指向下面准备的公开源码与解释器。`export_dir` 必须是已存在、位于档案和来源之外的独立本地目录。未安装的平台删掉对应配置项。

仅查 QQ 不需要 CaptureNext 或额外 Python 包。若查微信，可从可信渠道按部署需要核对依赖版本并创建独立虚拟环境：

```powershell
git clone --branch v0.1.1 --depth 1 https://github.com/lin522026298/CaptureNext.git
python -m venv ./CaptureNext/.venv
& ./CaptureNext/.venv/Scripts/python.exe -m pip install -r ./CaptureNext/requirements.txt
```

配置后，在有本机工具权限的 Agent 会话中可直接让它使用 `$local-chat-archive`，也可手工检查（从仓库运行 CLI 时显式传 `--profile`；下例从已安装技能运行）：

```powershell
$chat = Join-Path $skill 'scripts/chat_archive.py'
python $chat qq accounts
python $chat wechat accounts
```

实际要求示例：“用刚确认的 QQ 账号，在指定群里搜合同，给我消息前后文；只有原件能验证才保存一份。”详细选参及取件见 [技能](local-chat-archive/SKILL.md) 和 [使用说明](local-chat-archive/references/usage.md)。

查找“改过的那份”时，先用会话前后文确定哪条消息指向修订版，再验证那条消息的原件。微信旧版源码可能漏识别另存时自动加编号的同名文件；更新技能指引本身不能替代更新 `source_dir` 指向的 CaptureNext 源码。

升级可把新源码和虚拟环境放在独立目录，先保留旧版技能和私有配置备份，再更新技能及 `source_dir`、`python` 两项。若需要回退，恢复旧技能和对应旧配置；无需改动正式档案。只读查询不需要重新取钥；若确认采集因当前密钥失效而中断，请按[归档工具的密钥故障排查](https://github.com/lin522026298/CaptureNext/blob/v0.1.1/docs/configuration.md#密钥不可用时)处理。

## 验收与隐私

用隔离 Agent 对各自的双账号合成档案执行查找、上下文核对、确证附件导出及字节校验；同时验证了另一账号和同名弱候选不会被当成原件。微信有额外的文件、图片、原生语音和并发 WAL 读取回归。该覆盖不代表任意客户端版本、档案和媒体都能读取。

准备好上述 CaptureNext 源码与虚拟环境后，可从本仓库根目录复跑微信合成测试：

```powershell
$env:PYTHONPATH = (Resolve-Path './CaptureNext').Path
& ./CaptureNext/.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_wechat_reader.py' -v
```

脚本只处理已配置的授权本地档案，不联网传输聊天或附件，不自动执行文件、发送消息、登录或取得密钥。使用云 Agent 并把聊天文本送入其上下文时，仍可能发生由 Agent 服务处理的数据传输；请限定读取范围，敏感内容尽量用本地模式。Issue 只发合成问题，不提交私有配置、运行输出、聊天、附件或密钥。

本仓库代码按 [GPL-3.0](LICENSE) 分发，不含两个归档工具的二进制或数据。CaptureNext 与 QQArchiveNext 由各自仓库提供；本项目不代表腾讯官方。

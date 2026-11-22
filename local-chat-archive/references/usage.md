# 查询和取件

脚本用 `python $chat <平台> <操作>` 调用，`$chat` 见 SKILL.md。结果为 JSON，`--account` 必填（仅 `accounts` 除外），使用 `accounts` 当前给出的 `account`，不是聊天对象、群名或备注。`--help` 可单独查看入口。命令中的“账号标识”“消息ID”等为用户确认或上一调用返回的值，不是默认账号。

隔离验收时将 `--profile` 放在平台名之前，例如 `python $chat --profile $fixtureProfile qq accounts`；不要先运行默认账号列举再切换。

## 微信 CaptureNext

```powershell
python $chat wechat conversations --account '账号标识' --query '会话名'
python $chat wechat search --account '账号标识' --query '关键词' --limit 10
python $chat wechat search --account '账号标识' --conversation 'conversation_id' --query '关键词' --since '2026-11-01T00:00:00+08:00' --until '2026-11-19T00:00:00+08:00'
python $chat wechat messages --account '账号标识' --conversation 'conversation_id' --since '2026-11-18T00:00:00+08:00' --limit 20
python $chat wechat context --account '账号标识' --id 'logical_id' --limit 12
python $chat wechat attachments --account '账号标识' --id 'logical_id'
```

`search` 返回正文、稳定 `logical_id`、时间和会话；用 `context` 查前后文、`detail` 查观察版本及冲突（仅明确需要时）。部分关键词可能命中历史观察，代表正文并非必然命中，用 `detail` 核对。按 `next_offset` 翻页；时间用带时区的 ISO 8601，`since` 含、`until` 不含；如需包括某天，结束边界用下一天的零点。`attachments` 的图片、文件／视频列表是候选，可用分别返回的 `next_after` 配合 `--after-image`、`--after-file` 翻页。

“刚发的”“这版”“改完了”要在同一会话里核对前后文：一句话或一条引用不是文件卡片，也不一定指向紧邻的附件。先定位对应文件消息，再对它自己的 `logical_id` 取候选；不要拿另一条同名文件的校验值或下载目录里的旧件替代。没有关键词时用 `messages`，按时间缩小范围并跟随分页。

```powershell
python $chat wechat export --account '账号标识' --id 'logical_id' --kind file --sha 'file_sha' --name '验收文件.pdf'
```

`--kind video` 同理。如果 `file_video.hints[].md5` 有目标版本的明示校验值，先排除与该证据大小不符的候选（`evidence[].length_matches=false`），再交给导出复验。微信保存时可能加 `(2)` 等重名后缀；后缀和大小只用于发现候选。若同一目标版本仍有多个候选，逐个复验；`original_missing_or_not_confirmed_for_this_message` 只排除当前所选候选，若目标文件名仍不存在，可用它继续试同一消息的下一候选。若消息本身有多个仍无法区分的版本，先确认用户所指，不要试到哪个成功就用哪个。接口没有匹配项时，只报告“尚未确认／取出”，不要据此断言原件未归档。成功以 `status=linked` 和 `export_readback_verified=true` 为准，仍不证明物理来源。

原生可证语音用 `--kind voice` 和 `voice.rows` 的 `file_sha`，返回归档的原生字节，不冒称已转 WAV。图片用 `--kind image --sha ... --expected-md5 ...`，MD5 必须来自 `image.hints` 中非 `thumbnail` 的消息内容字段，输出的是校验过的解码图片，不是客户端密文；需要额外密钥或无法解码时报告缺口，不自动取钥。

此入口基于 CaptureNext 正式归档的只读事务，支持识别已登记的恢复接管目标；不启动桌面、WebUI 或采集、不打开微信源库。维护时暂时不可用则稍后重试，不跳过 WAL 或启动写者。

文件／图片候选来自共享内容库，不代表候选物理来源属于所选账号。只读入口不返回未归属的候选来源路径；没有当前消息自己的明示内容摘要时，不列出仅靠名称或缩略图匹配的共享候选。

## QQ Archive Next

```powershell
python $chat qq conversations --account '账号标识' --query '会话名'
python $chat qq search --account '账号标识' --query '关键词' --limit 10
python $chat qq context --account '账号标识' --conversation 'conversation.key' --id 'msg_id' --limit 12
python $chat qq attachments --account '账号标识' --table group_messages --id 'msg_id'
```

从搜索返回的 `conversation.key` 取会话标识；`conversation.source_table` 是 `group_messages` 或 `c2c_messages`，不是联系人名称。用 `context` 查看消息全文和前后文、`detail` 查看来源版本；64 位 `msg_id` 一直按字符串传递，别转 JSON 数字或科学计数法。`search --conversation` 可缩小返回会话，但会在原始搜索页之后筛选，要跟随 `next_offset` 查看后续页。较短关键词可能慢；不默认扩大到其他账号或历史工具。

```powershell
python $chat qq export --account '账号标识' --table group_messages --id 'msg_id' --segment 0 --sha 'sha256' --name '照片.png'
```

从 `attachments` 返回的 `items` 中选择 `status=verified_original` 的项，用其 `segment`、`sha256`；命令会再次核对账号、消息表、消息 ID、段号与原件 SHA-256，不直接把归档原件交给编辑器。预览、候选、缺失或无可核实摘要均不能当作原件。`items=[]` 不区分消息不在该账号／表，与消息存在但没有媒体；先回到原搜索结果核对。QQ 读取使用安装的 QQArchiveCore 自带 `agent call` 接口，不调用 `capture`、`watch`、登录或密钥工具。

## 本地配置与产物

`local.private.json` 只记录本机软件路径和独立取件目录，不记录聊天、密钥或账号选择。其他设备显式提供 `--profile`：顶层 `export_dir` 为已有本地目录，`wechat` 为 `{ "source_dir": "CaptureNext 源码根", "python": "含依赖的 Python.exe", "root": "安装根" }`，`qq` 为 `{ "core": "QQArchiveCore.exe", "state": "QQ 正式档案目录" }`；只安装一个平台就省略另一个键。微信需要与档案版本兼容的 CaptureNext 源码及 Python 运行环境，取件和检索调用该源码自带的只读入口，不要求修改 CaptureNext 源码。QQ 的旧导出/迁移包先按其产品流程成为可打开的档案，不自动解包或尝试旧格式。各自安装了多份或需查指定的恢复档案时，为每一份建独立 profile，再由用户选择，不猜根目录。导出只接受独立目录中的新单文件名；也可通过配置把取件目录指定到用户要求且已存在的安全目录。

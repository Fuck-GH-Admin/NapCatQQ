# NoQQ OneBot v11 Simulator (独立测试程序)

用于替代 NapCat→QQ 账号链路进行 **AstrBot / 大肥鱼的离线消息测试**。这是独立 Python 实现，**不导入、不修改 NapCat 源码**，不会向腾讯 QQ 网络登录或发送消息。

## 快速启动

Python 3.12+：

```bash
python -m pip install -r tools/noqq-onebot-sim/requirements.txt
python tools/noqq-onebot-sim/simulator.py \
  --url ws://127.0.0.1:6199/ws \
  --script tools/noqq-onebot-sim/scenario.example.jsonl \
  --log ./local-noqq-evidence.jsonl
```

不指定 `--script` 就是交互式终端：可以聊天，也可以输入 `/json [{"type":"image","data":{"file":"..."}}]` 发送 OneBot 多媒体消息段。

AstrBot 必须开启一个 **OneBot v11 / aiocqhttp 反向 WebSocket 监听端**，并与测试脚本采用相同的 token（如有）。可用 `--token` 传入；敏感 token 不建议写在命令历史中。对于容器网络地址，如 `ws://astrbot:6199/ws`，必须另外加 `--allow-remote`，并且只能放在隔离受信的 Docker 网络，不要公网暴露。

大肥鱼的当前私聊准入逻辑需要以下 *测试专用* 设置：

- `DAFEIYU_PRIVATE_UMO=aiocqhttp:FriendMessage:123456789`
- AstrBot 平台 ID 为 `aiocqhttp`，原生白名单只允许 `aiocqhttp:FriendMessage:123456789`，管理员豁免关闭
- 模拟 Bot ID `987654321`，测试人 ID `123456789`；对应 AstrBot 配置独立于生产数据目录

> 注意：如果 AstrBot 平台 ID 不是 `aiocqhttp`，要一起调整 UMO 和白名单。与真实 QQ 的连接不应在同一个隔离实例中并行运行。


## 真正可用的接入方法（替换 NapCat）

让 AstrBot 继续使用原生 `aiocqhttp` OneBot v11 平台，**不要同时运行真实 NapCat 和 NoQQ**。虚拟 Bot 的 ID 是 `987654321`，虚拟测试用户的 ID 是 `123456789`。

在隔离 AstrBot `data/cmd_config.json` 中确认平台和白名单（下列仅为相关字段，请合并到既有配置，不要覆盖整份文件）：

```json
{
  "platform": [{
    "id": "aiocqhttp",
    "type": "aiocqhttp",
    "enable": true,
    "ws_reverse_host": "0.0.0.0",
    "ws_reverse_port": 6199,
    "ws_reverse_token": "本机测试口令"
  }],
  "platform_settings": {
    "enable_id_white_list": true,
    "id_whitelist": ["aiocqhttp:FriendMessage:123456789"],
    "wl_ignore_admin_on_friend": false,
    "wl_ignore_admin_on_group": false,
    "friend_message_needs_wake_prefix": false
  }
}
```

大肥鱼进程设置 `DAFEIYU_PRIVATE_UMO=aiocqhttp:FriendMessage:123456789`。OneBot token 设置为 `NOQQ_WS_TOKEN` 环境变量（与 AstrBot 配置一致），不要把 token 提交到仓库。

同一主机运行（AstrBot 的 6199 端口已经可从宿主机连接）：

```bash
export NOQQ_WS_TOKEN='本机测试口令'
python tools/noqq-onebot-sim/simulator.py --url ws://127.0.0.1:6199/ws
```

若使用仓库的 `compose.acceptance.yaml`，6185 对外、6199 仅 `expose` 给 Docker 网络，因此**宿主机直接连接 127.0.0.1:6199 会失败**。此时使用同网络容器代替 NapCat：

```bash
docker build -t dafeiyu-noqq -f tools/noqq-onebot-sim/Dockerfile tools/noqq-onebot-sim
docker run --rm -it   --network dafeiyu-p1-bot-core   -e NOQQ_WS_TOKEN   dafeiyu-noqq --url ws://dafeiyu-p1-astrbot:6199/ws --allow-remote
```

上述 Docker 构建使用官方 `python:3.12-slim` 多架构基础镜像，支持 amd64 / arm64 的常规 Linux Docker 环境。请先停止原 NapCat-B/T 容器，确保只有一个模拟客户端连接这个 AstrBot 端口。

### 真实测试媒体

用 `--media-dir /path/to/fixtures` 指定一个只存**合成素材**的目录。交互输入 `/image image.png`、`/voice audio.wav`、`/video clip.mp4`，程序会返回带随机 token 的只读 HTTP 文件 URL，而不只是假的媒体路径。若 AstrBot 在不同容器，需要把 `--media-bind` 与 `--media-host` 配成 AstrBot 真正可到达的地址和同网络访问路径。音频转码、QQ SILK 格式与真正客户端播放仍不属于该模拟端的功能。

### 验收边界

- **已通过**：官方 AstrBot v4.29.3 实际 `AiocqhttpAdapter` 与真实 WebSocket 之间的来回收发（不是 CQHttp Mock），以及文件服务 HTTP 字节下载的独立测试。
- **正在独立验证**：大肥鱼插件与整个 AstrBot Core 的多轮消息和 SQLite 记忆链路；以其仓库独立 CI 结果为准，不能拿协议通过替代。
- **没有声称**：模拟腾讯 QQ 在线状态、QQ 多端真实投递、真实客户端播放或完整 NapCat 扩展 API 兼容。


## 范围

- **真实** OneBot v11 反向 WebSocket 协议帧：事件推送、动作处理、`echo` 回传、连接元事件和心跳。
- 目前实现：私聊、单个模拟群、文本和 OneBot `image` / `record` / `video` / `face` / `reply` / `file` 等消息段透传，获取消息、模拟用户资料、基本状态、删除消息、假回执。
- `--script` 提供逐轮等待回答的 JSONL 驱动。失败或超时不会擅自重发；失败时停止，以免把旧回复错记到下一轮。
- `--log` 可选保存消息与回执，其中包含**完整测试正文**，只可使用合成数据，切勿提交真实私人聊天记录。
- `get_image` / `get_record` 等操作只返回引用，不做图片下载、音频转码或视频播放。媒体本体需通过独立共享目录或 HTTP 文件服务提供给 AstrBot 容器；**消息段通过不代表真实媒体可访问或可播放**。
- 不模拟 QQ 在线、真实好友关系、QQ 服务器重连语义，也不宣称覆盖全部 NapCat 扩展 API。未知动作明确返回失败。

## 测试

```bash
python -m unittest discover -s tools/noqq-onebot-sim -p 'test_*.py' -v
```

该测试使用本地临时 WebSocket 服务端模拟 AstrBot 的动作请求，不需要 QQ 登录；**不等同于已完成 AstrBot Core / 大肥鱼插件整链路验收**。下一步集成到大肥鱼的隔离 AstrBot 4.29.3 Core 运行器，检查对话上下文、持久化记忆与媒体解码。

## 约束

本目录为原创、独立协议测试器，未从 NapCat 移植 NTQQ 登录、内核 API 或媒体模块。fork 的 `LICENSE` 对修改/分发有额外要求，应在任何公开发布前先确认许可条件；该测试器不修改其核心代码。

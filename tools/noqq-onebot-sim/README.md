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

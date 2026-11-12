#!/usr/bin/env python3
"""Integration test against unmodified AstrBot v4.29.3 aiocqhttp adapter.

Invoke from checkout of pinned AstrBot repo, with its requirements installed:
PYTHONPATH=$ASTRBOT_SOURCE python /path/to/integration_astrbot_adapter.py
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
from pathlib import Path
import socket
import sys
import tempfile

from simulator import OneBotSimulator


async def main() -> None:
    from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import AiocqhttpAdapter
    from astrbot.core.message.components import Plain
    from astrbot.core.message.message_event_result import MessageChain

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    event_queue: asyncio.Queue = asyncio.Queue()
    adapter = AiocqhttpAdapter(
        {
            "id": "aiocqhttp",
            "type": "aiocqhttp",
            "ws_reverse_host": "127.0.0.1",
            "ws_reverse_port": port,
            "ws_reverse_token": "",
        },
        {},
        event_queue,
    )
    adapter_task = asyncio.create_task(adapter.run())
    try:
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / "scenario.jsonl"
            script.write_text(
                json.dumps({"message": [
                    {"type": "text", "data": {"text": "真正的 AstrBot 收到了我吗？"}},
                    {"type": "face", "data": {"id": 13}},
                ]}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            sim = OneBotSimulator(987654321, 123456789)
            sim_task = None
            for attempt in range(35):
                if adapter_task.done():
                    raise AssertionError(f"AstrBot adapter exited: {adapter_task.exception()}")
                try:
                    sim_task = asyncio.create_task(sim.run(
                        url=f"ws://127.0.0.1:{port}/ws",
                        token="",
                        script=script,
                        timeout=15,
                        heart_interval=30,
                    ))
                    event = await asyncio.wait_for(event_queue.get(), timeout=1.5)
                    break
                except (ConnectionError, OSError, asyncio.TimeoutError):
                    if sim_task:
                        sim_task.cancel()
                        await asyncio.gather(sim_task, return_exceptions=True)
                    if not event_queue.empty():
                        raise
                    await asyncio.sleep(0.15)
            else:
                raise AssertionError("simulator did not reach real AstrBot adapter")
            assert event.get_sender_id() == "123456789", event.get_sender_id()
            assert event.unified_msg_origin == "aiocqhttp:FriendMessage:123456789", event.unified_msg_origin
            assert "真正的 AstrBot" in event.message_str, event.message_str
            assert any(getattr(item, "type", "").lower() == "face" for item in event.message_obj.message)

            # The actual AstrBot AiocqhttpMessageEvent.send converts its chain
            # to send_private_msg, routes it through CQHttp over real WS and
            # awaits our OneBot action response (not AsyncMock).
            await asyncio.wait_for(
                event.send(MessageChain([Plain("AstrBot 真正收到了，且完成 OneBot 回传。")])),
                timeout=15,
            )
            outcome = await asyncio.wait_for(sim_task, timeout=15)
            assert outcome == 0, outcome
            assert len(sim.receipts) == 1, sim.receipts
            reply = sim.receipts[0]["record"]
            assert reply["message_type"] == "private", reply
            assert reply["message"][0]["data"]["text"].startswith("AstrBot 真正收到了"), reply
            assert sim.receipts[0]["action"] == "send_private_msg"
            print("REAL_ASTRBOT_4293_ADAPTER_FULL_DUPLEX_PASS")
    finally:
        await adapter.terminate()
        adapter_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await asyncio.wait_for(adapter_task, timeout=10)


if __name__ == "__main__":
    asyncio.run(main())

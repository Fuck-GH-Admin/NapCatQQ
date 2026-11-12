"""Local contract tests, requiring no QQ, AstrBot, NapCat, or model credentials."""
from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from websockets.asyncio.server import serve
from simulator import OneBotSimulator, segments


class UnitTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.sim = OneBotSimulator(987654321, 123456789)

    def test_segments_passthrough(self):
        image = [{"type": "text", "data": {"text": "看图"}}, {"type": "image", "data": {"file": "file:///tmp/fixture.png", "url": "http://127.0.0.1/test.png"}}]
        audio = [{"type": "record", "data": {"file": "file:///tmp/fixture.wav"}}]
        video = [{"type": "video", "data": {"file": "file:///tmp/fixture.mp4"}}]
        self.assertEqual(segments(image), image)
        self.assertEqual(segments(audio), audio)
        self.assertEqual(segments(video), video)
        with self.assertRaises(ValueError):
            segments([{"type": "unsupported", "data": {}}])

    async def test_actions_and_privacy(self):
        sim = self.sim
        result = await sim._dispatch_action({"action": "get_login_info"})
        self.assertEqual(result["data"]["user_id"], 987654321)
        result = await sim._dispatch_action({"action": "send_private_msg", "params": {"user_id": 123456789, "message": [{"type": "record", "data": {"file": "voice.wav"}}]}})
        self.assertEqual(result["retcode"], 0)
        msg = sim.messages[result["data"]["message_id"]]
        self.assertEqual(msg["message"][0]["type"], "record")
        self.assertEqual(len(sim.receipts), 1)
        result = await sim._dispatch_action({"action": "send_private_msg", "params": {"user_id": 567894321, "message": "private"}})
        self.assertEqual(result["retcode"], 1403)
        self.assertEqual(len(sim.receipts), 1)
        result = await sim._dispatch_action({"action": "unknown_side_effect", "params": {}})
        self.assertNotEqual(result["retcode"], 0)
        result = await sim._dispatch_action({"action": "send_group_msg", "params": {"group_id": 87654321, "message": "group"}})
        self.assertEqual(result["retcode"], 0)
        self.assertEqual(len(sim.receipts), 2)
        result = await sim._dispatch_action({"action": "get_msg", "params": {"message_id": sim.receipts[0]["record"]["message_id"]}})
        self.assertEqual(result["data"]["message_type"], "private")

    async def test_jsonl_full_duplex_reverse_ws(self):
        seen = []
        async def astrbot_stub(ws):
            self.assertEqual(ws.request.headers["X-Self-ID"], "987654321")
            self.assertEqual(ws.request.headers["X-Client-Role"], "Universal")
            async for raw in ws:
                payload = json.loads(raw)
                seen.append(payload)
                if payload.get("post_type") == "message":
                    await ws.send(json.dumps({"action": "send_private_msg", "params": {"user_id": payload["user_id"], "message": [{"type": "text", "data": {"text": "模拟答复"}}, {"type": "face", "data": {"id": 13}}]}, "echo": "msg-1"}))
                elif payload.get("echo") == "msg-1":
                    self.assertEqual(payload["retcode"], 0)
                    self.assertIsInstance(payload["data"]["message_id"], int)
                    break
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scenario.jsonl"
            path.write_text(json.dumps({"message": "你好", "expect_reply": True}, ensure_ascii=False) + "\n", encoding="utf-8")
            async with serve(astrbot_stub, "127.0.0.1", 0) as server:
                port = server.sockets[0].getsockname()[1]
                result = await self.sim.run(url=f"ws://127.0.0.1:{port}/ws", token="", script=path, timeout=2, heart_interval=10)
            self.assertEqual(result, 0)
            self.assertTrue(any(event.get("post_type") == "message" for event in seen))
            self.assertEqual(len(self.sim.receipts), 1)
            self.assertEqual(self.sim.receipts[0]["record"]["message"][1]["type"], "face")

    async def test_no_reply_times_out_without_resend(self):
        seen = []
        async def silent_server(ws):
            async for raw in ws:
                message = json.loads(raw)
                if message.get("post_type") == "message":
                    seen.append(message)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scenario.jsonl"
            path.write_text('{"message":"hello","timeout":0.1}\n')
            async with serve(silent_server, "127.0.0.1", 0) as server:
                port = server.sockets[0].getsockname()[1]
                result = await self.sim.run(url=f"ws://127.0.0.1:{port}/ws", token="", script=path, timeout=.1, heart_interval=10)
            self.assertEqual(result, 1)
            self.assertEqual(len(seen), 1)
            self.assertEqual(len(self.sim.receipts), 0)


if __name__ == "__main__":
    unittest.main()

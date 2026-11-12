#!/usr/bin/env python3
"""Independent, login-free OneBot v11 reverse-WebSocket peer for AstrBot tests.

No NapCat / NTQQ code is imported. This is intentionally a *partial* OneBot
implementation; unknown actions fail instead of claiming QQ-side success.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

from websockets.asyncio.client import connect

LOG = logging.getLogger("noqq-onebot")
ID_PATTERN = re.compile(r"^[1-9][0-9]{4,19}$")
SUPPORTED_SEGMENTS = {"text", "image", "record", "video", "face", "at", "reply", "file", "json", "xml", "node"}


def numeric_id(value: object) -> int:
    if isinstance(value, bool) or not ID_PATTERN.fullmatch(str(value)):
        raise ValueError(f"expected a synthetic numeric ID, got {value!r}")
    return int(str(value))


def segments(message: object) -> list[dict]:
    if isinstance(message, str):
        return [{"type": "text", "data": {"text": message}}]
    if not isinstance(message, list) or not message:
        raise ValueError("message must be a nonempty string or OneBot segment array")
    clean = []
    for item in message:
        if not isinstance(item, dict) or item.get("type") not in SUPPORTED_SEGMENTS or not isinstance(item.get("data"), dict):
            raise ValueError("invalid/unsupported OneBot message segment")
        clean.append({"type": item["type"], "data": dict(item["data"])})
    return clean


def plaintext(parts: list[dict]) -> str:
    return "".join(str(p["data"].get("text", "")) if p["type"] == "text" else f"[{p['type']}]" for p in parts)


class OneBotSimulator:
    def __init__(self, bot_id: int, user_id: int, nickname: str = "NoQQ Tester", group_id: int = 87654321):
        self.bot_id, self.user_id, self.nickname, self.group_id = bot_id, user_id, nickname, group_id
        self._next_id = 100000
        self.messages: dict[int, dict] = {}
        self.receipts: list[dict] = []
        self.inbox: dict[tuple[str, int], asyncio.Queue] = defaultdict(asyncio.Queue)
        self.websocket = None
        self.log_path: Path | None = None

    def _id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _event(self, sender_id: int, parts: list[dict], *, group_id: int | None = None) -> dict:
        ident = self._id()
        event = {
            "time": int(time.time()), "self_id": self.bot_id,
            "post_type": "message", "message_type": "group" if group_id is not None else "private",
            "sub_type": "normal" if group_id is not None else "friend",
            "message_id": ident, "user_id": sender_id, "message": parts,
            "raw_message": plaintext(parts), "font": 0,
            "sender": {"user_id": sender_id, "nickname": self.nickname, "sex": "unknown", "age": 0},
        }
        if group_id is not None:
            event["group_id"] = group_id
            event["sender"].update({"card": self.nickname, "role": "member", "title": ""})
        self.messages[ident] = event
        return event

    async def inject(self, message: object, *, user_id: int | None = None, group_id: int | None = None) -> dict:
        if self.websocket is None:
            raise RuntimeError("not connected")
        uid = user_id or self.user_id
        event = self._event(uid, segments(message), group_id=group_id)
        await self.websocket.send(json.dumps(event, ensure_ascii=False))
        self._log({"direction": "inbound", "event": event})
        print(f"[tester:{uid} -> bot] {plaintext(event['message'])}", flush=True)
        return event

    def _log(self, record: dict) -> None:
        if self.log_path is None:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")

    async def _dispatch_action(self, request: dict) -> dict:
        action = str(request.get("action", ""))
        params = request.get("params") or {}
        if not isinstance(params, dict):
            return self._response(None, 1400, "invalid params")
        try:
            if action in ("send_private_msg", "send_group_msg", "send_msg"):
                is_group = action == "send_group_msg" or (action == "send_msg" and params.get("message_type") == "group")
                target = numeric_id(params.get("group_id") if is_group else params.get("user_id"))
                # Simulated inbound friend IDs are controlled fixtures, not arbitrary external recipients.
                if is_group and target != self.group_id:
                    return self._response(None, 1403, "unknown synthetic group")
                if not is_group and target != self.user_id:
                    return self._response(None, 1403, "unknown synthetic recipient")
                msg = segments(params.get("message"))
                ident = self._id()
                record = {
                    "time": int(time.time()), "message_id": ident, "self_id": self.bot_id,
                    "post_type": "message", "message_type": "group" if is_group else "private",
                    "sub_type": "normal" if is_group else "friend", "user_id": self.bot_id,
                    "message": msg, "raw_message": plaintext(msg),
                    "sender": {"user_id": self.bot_id, "nickname": "NoQQ Bot"},
                }
                if is_group:
                    record["group_id"] = target
                self.messages[ident] = record
                receipt = {"action": action, "params": params, "record": record}
                self.receipts.append(receipt)
                self._log({"direction": "outbound", **receipt})
                await self.inbox[("group" if is_group else "private", target)].put(receipt)
                print(f"[bot -> {'group' if is_group else 'tester'}:{target}] {plaintext(msg)}", flush=True)
                return self._response({"message_id": ident})
            if action == "get_login_info":
                return self._response({"user_id": self.bot_id, "nickname": "NoQQ Bot"})
            if action == "get_status":
                return self._response({"online": True, "good": True})
            if action == "get_version_info":
                return self._response({"app_name": "NoQQ OneBot Simulator", "app_version": "0.1.0", "protocol_version": "v11"})
            if action == "get_friend_list":
                return self._response([{"user_id": self.user_id, "nickname": self.nickname, "remark": ""}])
            if action == "get_stranger_info":
                uid = numeric_id(params.get("user_id"))
                if uid not in (self.user_id, self.bot_id):
                    return self._response(None, 1404, "unknown user")
                return self._response({"user_id": uid, "nickname": self.nickname if uid == self.user_id else "NoQQ Bot", "sex": "unknown", "age": 0})
            if action == "get_group_list":
                return self._response([{"group_id": self.group_id, "group_name": "NoQQ Group", "member_count": 2, "max_member_count": 10}])
            if action == "get_group_info":
                gid = numeric_id(params.get("group_id"))
                if gid != self.group_id:
                    return self._response(None, 1404, "unknown group")
                return self._response({"group_id": gid, "group_name": "NoQQ Group", "member_count": 2, "max_member_count": 10})
            if action == "get_group_member_list":
                if numeric_id(params.get("group_id")) != self.group_id:
                    return self._response(None, 1404, "unknown group")
                return self._response([{"group_id": self.group_id, "user_id": uid, "nickname": name, "card": "", "role": role} for uid, name, role in ((self.bot_id, "NoQQ Bot", "owner"), (self.user_id, self.nickname, "member"))])
            if action == "get_msg":
                ident = int(params.get("message_id"))
                if ident not in self.messages:
                    return self._response(None, 1404, "unknown message")
                return self._response(self.messages[ident])
            if action == "delete_msg":
                ident = int(params.get("message_id"))
                if ident not in self.messages:
                    return self._response(None, 1404, "unknown message")
                del self.messages[ident]
                return self._response({})
            if action in ("can_send_image", "can_send_record"):
                return self._response({"yes": True})
            if action in ("get_image", "get_record", "get_file"):
                # No media conversion or downloads: give back the fixture URI exactly.
                uri = params.get("file")
                if not isinstance(uri, str) or not uri:
                    return self._response(None, 1400, "media fixture path required")
                return self._response({"file": uri})
        except (ValueError, TypeError, KeyError) as exc:
            return self._response(None, 1400, f"invalid params: {type(exc).__name__}")
        return self._response(None, 1404, f"unsupported action: {action}")

    @staticmethod
    def _response(data: object, retcode: int = 0, message: str = "") -> dict:
        return {"status": "ok" if retcode == 0 else "failed", "retcode": retcode,
                "data": data, "message": message, "wording": message}

    async def handle_frame(self, frame: str) -> None:
        try:
            request = json.loads(frame)
        except json.JSONDecodeError:
            LOG.warning("ignored malformed OneBot action frame")
            return
        if not isinstance(request, dict) or not isinstance(request.get("action"), str):
            LOG.debug("ignored non-action frame")
            return
        result = await self._dispatch_action(request)
        if "echo" in request:
            result["echo"] = request["echo"]
        if self.websocket is not None:
            await self.websocket.send(json.dumps(result, ensure_ascii=False))

    async def receive_loop(self) -> None:
        async for frame in self.websocket:
            await self.handle_frame(frame)

    async def heartbeat(self, seconds: float) -> None:
        while True:
            await asyncio.sleep(seconds)
            await self.websocket.send(json.dumps({
                "time": int(time.time()), "self_id": self.bot_id, "post_type": "meta_event",
                "meta_event_type": "heartbeat", "status": {"online": True, "good": True},
                "interval": int(seconds * 1000),
            }))

    async def run_script(self, script: Path, timeout: float) -> int:
        failures = 0
        for line_num, line in enumerate(script.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            case = json.loads(line)
            if not isinstance(case, dict):
                raise ValueError(f"line {line_num}: expected object")
            if "wait_seconds" in case:
                await asyncio.sleep(float(case["wait_seconds"]))
                continue
            uid = numeric_id(case.get("user_id", self.user_id))
            gid = numeric_id(case["group_id"]) if case.get("group_id") is not None else None
            key = ("group", gid) if gid is not None else ("private", uid)
            # Do not silently attribute a delayed previous answer to a new turn.
            if not self.inbox[key].empty():
                LOG.error("pending unclaimed reply before line %s; stopping", line_num)
                return 1
            await self.inject(case["message"], user_id=uid, group_id=gid)
            if not case.get("expect_reply", True):
                continue
            try:
                receipt = await asyncio.wait_for(self.inbox[key].get(), timeout=float(case.get("timeout", timeout)))
                if not receipt["record"]["message"]:
                    raise ValueError("empty reply")
            except (asyncio.TimeoutError, ValueError):
                failures += 1
                LOG.error("line %s: no valid reply; will not resend automatically", line_num)
                # Unknown delivery: fail closed and stop; moving on could mismatch later turns.
                break
        return 1 if failures else 0

    async def interactive(self) -> None:
        print("NoQQ interactive chat. Type /quit to exit, or /json <OneBot segment JSON array>.")
        while True:
            try:
                entry = await asyncio.to_thread(input, "> ")
            except (EOFError, KeyboardInterrupt):
                return
            if entry.strip() == "/quit":
                return
            if not entry.strip():
                continue
            payload = json.loads(entry[6:]) if entry.startswith("/json ") else entry
            await self.inject(payload)

    async def run(self, *, url: str, token: str, script: Path | None, timeout: float, heart_interval: float) -> int:
        headers = {"X-Self-ID": str(self.bot_id), "X-Client-Role": "Universal", "User-Agent": "NoQQ-OneBot-Sim/0.1"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with connect(url, additional_headers=headers, max_size=16 * 1024 * 1024) as ws:
            self.websocket = ws
            receiver = asyncio.create_task(self.receive_loop())
            heart = asyncio.create_task(self.heartbeat(heart_interval))
            try:
                await ws.send(json.dumps({"time": int(time.time()), "self_id": self.bot_id,
                    "post_type": "meta_event", "meta_event_type": "lifecycle", "sub_type": "connect"}))
                await asyncio.sleep(0.1)
                return await self.run_script(script, timeout) if script else (await self.interactive() or 0)
            finally:
                heart.cancel()
                receiver.cancel()
                await asyncio.gather(heart, receiver, return_exceptions=True)
                self.websocket = None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Login-free OneBot v11 reverse WebSocket simulator")
    parser.add_argument("--url", default="ws://127.0.0.1:6199/ws", help="AstrBot reverse WS URL")
    parser.add_argument("--token", default="", help="Optional AstrBot reverse WS bearer token")
    parser.add_argument("--bot-id", default="987654321")
    parser.add_argument("--user-id", default="123456789")
    parser.add_argument("--group-id", default="87654321")
    parser.add_argument("--script", type=Path, help="JSONL script; otherwise interactive mode")
    parser.add_argument("--log", type=Path, help="Local JSONL evidence (contains complete message text)")
    parser.add_argument("--timeout", type=float, default=40.0)
    parser.add_argument("--heartbeat", type=float, default=30.0)
    parser.add_argument("--allow-remote", action="store_true", help="Permit a non-local ws:// endpoint")
    args = parser.parse_args(argv)
    parsed = urlparse(args.url)
    if parsed.scheme not in {"ws", "wss"} or not parsed.hostname:
        parser.error("--url must be ws:// or wss://")
    if parsed.scheme == "ws" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"} and not args.allow_remote:
        parser.error("plain ws:// outside localhost requires --allow-remote (use only trusted Docker networks)")
    if args.timeout <= 0 or args.heartbeat <= 0:
        parser.error("timeout and heartbeat must be positive")
    if args.script is not None and not args.script.is_file():
        parser.error("script does not exist")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sim = OneBotSimulator(numeric_id(args.bot_id), numeric_id(args.user_id), group_id=numeric_id(args.group_id))
    sim.log_path = args.log
    try:
        return asyncio.run(sim.run(url=args.url, token=args.token, script=args.script,
                                   timeout=args.timeout, heart_interval=args.heartbeat))
    except (OSError, TimeoutError, ConnectionError) as exc:
        LOG.error("connection failed: %s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())

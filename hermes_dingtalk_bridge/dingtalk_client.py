from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import platform
import socket
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import quote_plus

import requests
import websockets

from .config import BridgeConfig

logger = logging.getLogger(__name__)


class DingTalkApiError(RuntimeError):
    pass


class DingTalkClient:
    OPEN_CONNECTION_API = "https://api.dingtalk.com/v1.0/gateway/connections/open"

    def __init__(self, config: BridgeConfig) -> None:
        self.config = config
        self._access_token: Optional[str] = None

    def _json_request(
        self,
        method: str,
        url: str,
        payload: Optional[dict[str, Any]] = None,
        *,
        access_token: Optional[str] = None,
    ) -> dict[str, Any]:
        data = None
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if access_token:
            headers["x-acs-dingtalk-access-token"] = access_token
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.config.request_timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise DingTalkApiError(f"HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise DingTalkApiError(f"DingTalk API unreachable: {exc.reason}") from exc
        return json.loads(raw) if raw else {}

    def post_openapi(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._json_request(
            "POST",
            f"https://api.dingtalk.com{path}",
            payload,
            access_token=self.get_access_token(),
        )

    def get_access_token(self, *, force_refresh: bool = False) -> str:
        if self._access_token and not force_refresh:
            return self._access_token
        response = self._json_request(
            "POST",
            "https://api.dingtalk.com/v1.0/oauth2/accessToken",
            {"appKey": self.config.client_id, "appSecret": self.config.client_secret},
        )
        token = response.get("accessToken") or response.get("access_token")
        if not token:
            raise DingTalkApiError(f"Missing access token in response: {response}")
        self._access_token = str(token)
        return self._access_token

    def send_session_markdown(self, session_webhook: str, text: str) -> dict[str, Any]:
        token = self.get_access_token()
        title = text.splitlines()[0][:60] if text else "Hermes"
        return self._json_request(
            "POST",
            session_webhook,
            {"msgtype": "markdown", "markdown": {"title": title or "Hermes", "text": text}},
            access_token=token,
        )

    def send_proactive_markdown(self, conversation_id: str, text: str) -> dict[str, Any]:
        token = self.get_access_token()
        title = text.splitlines()[0][:60] if text else "Hermes"
        payload: dict[str, Any] = {
            "robotCode": self.config.client_id,
            "msgKey": "sampleMarkdown",
            "msgParam": json.dumps({"title": title or "Hermes", "text": text}),
        }
        if conversation_id.startswith("cid"):
            payload["openConversationId"] = conversation_id
            url = "https://api.dingtalk.com/v1.0/robot/groupMessages/send"
        else:
            payload["userIds"] = [conversation_id]
            url = "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend"
        return self._json_request("POST", url, payload, access_token=token)

    def upload_media(self, file_path: str | Path) -> dict[str, Any]:
        path = Path(file_path)
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        boundary = "----HermesDingTalkBridgeBoundary"
        parts = [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="type"\r\n\r\nfile\r\n',
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="media"; filename="{path.name}"\r\n'.encode(),
            f"Content-Type: {mime_type}\r\n\r\n".encode(),
            path.read_bytes(),
            f"\r\n--{boundary}--\r\n".encode(),
        ]
        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "x-acs-dingtalk-access-token": self.get_access_token(),
        }
        req = urllib.request.Request(
            "https://api.dingtalk.com/v1.0/robot/media/upload",
            data=b"".join(parts),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.config.request_timeout_seconds) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}

    def open_stream_connection(self, subscriptions: list[dict[str, str]]) -> dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"HermesDingTalkBridge/1.0 Python/{platform.python_version()}",
        }
        body = {
            "clientId": self.config.client_id,
            "clientSecret": self.config.client_secret,
            "subscriptions": subscriptions,
            "ua": "hermes-dingtalk-bridge/1.0",
            "localIp": self.get_host_ip(),
        }
        logger.info("open connection, url=%s", self.OPEN_CONNECTION_API)
        response = requests.post(self.OPEN_CONNECTION_API, headers=headers, data=json.dumps(body).encode("utf-8"), timeout=self.config.request_timeout_seconds)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def get_host_ip() -> str:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


class DingTalkStreamRunner:
    def __init__(
        self,
        config: BridgeConfig,
        on_message: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        self.config = config
        self._on_message = on_message
        self._stop = False
        self._websocket = None
        self._client = DingTalkClient(config)

    async def run_once(self) -> None:
        subscriptions = [
            {"type": "CALLBACK", "topic": "/v1.0/im/bot/messages/get"},
            {"type": "CALLBACK", "topic": "/v1.0/im/bot/messages/delegate"},
        ]
        connection = await asyncio.to_thread(self._client.open_stream_connection, subscriptions)
        logger.info("endpoint is %s", connection)
        uri = f"{connection['endpoint']}?ticket={quote_plus(connection['ticket'])}"
        websocket = await websockets.connect(uri)
        self._websocket = websocket
        keepalive = asyncio.create_task(self._keepalive(websocket))
        try:
            async for raw_message in websocket:
                await self._route_message(raw_message)
                if self._stop:
                    break
        finally:
            keepalive.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await keepalive
            with contextlib.suppress(Exception):
                await websocket.close()

    def request_stop(self) -> None:
        self._stop = True
        websocket = self._websocket
        if websocket is not None:
            asyncio.create_task(websocket.close())

    async def _keepalive(self, websocket, ping_interval: int = 60) -> None:
        while True:
            await asyncio.sleep(ping_interval)
            await websocket.ping()

    async def _route_message(self, raw_message: str) -> None:
        json_message = json.loads(raw_message)
        msg_type = json_message.get("type", "")
        if msg_type == "CALLBACK":
            headers = json_message.get("headers", {}) or {}
            data = json_message.get("data", {})
            if isinstance(data, str):
                data = json.loads(data)
            topic = headers.get("topic")
            logger.info(
                "Received DingTalk callback topic=%s message_id=%s msgId=%s conversationId=%s",
                topic,
                headers.get("messageId"),
                data.get("msgId"),
                data.get("conversationId"),
            )
            try:
                await self._on_message(data)
            except Exception:
                logger.exception("Error while processing DingTalk callback")
            await self._send_ack(headers.get("messageId"), topic)
        elif msg_type == "SYSTEM":
            headers = json_message.get("headers", {}) or {}
            if headers.get("topic") == "disconnect":
                await self._send_ack(headers.get("messageId"), headers.get("topic"))
                if self._websocket is not None:
                    await self._websocket.close()
        else:
            logger.debug("Ignoring DingTalk stream message type=%s", msg_type)

    async def _send_ack(self, message_id: Optional[str], topic: Optional[str]) -> None:
        if self._websocket is None or not message_id:
            return
        ack = {
            "code": 200,
            "headers": {
                "messageId": message_id,
                "contentType": "application/json",
                **({"topic": topic} if topic else {}),
            },
            "message": "",
            "data": json.dumps({"response": "OK"}),
        }
        await self._websocket.send(json.dumps(ack))


import contextlib

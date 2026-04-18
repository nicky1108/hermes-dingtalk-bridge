from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Callable, Optional

import requests

from .config import BridgeConfig
from .models import HermesReply


logger = logging.getLogger(__name__)


class HermesApiError(RuntimeError):
    pass


class HermesStreamFallbackRequested(HermesApiError):
    pass


class HermesClient:
    def __init__(self, config: BridgeConfig) -> None:
        self.config = config

    def _request(self, method: str, path: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        url = f"{self.config.hermes_api_base.rstrip('/')}{path}"
        data = None
        headers = {"Authorization": f"Bearer {self.config.hermes_api_key}"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, method=method, data=data, headers=headers)
        logger.debug("Hermes request %s %s payload_keys=%s", method, url, sorted(payload.keys()) if payload else [])
        try:
            with urllib.request.urlopen(req, timeout=self.config.request_timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                logger.debug("Hermes response %s %s len=%s", method, url, len(raw))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise HermesApiError(f"HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise HermesApiError(f"Hermes API unreachable: {exc.reason}") from exc
        if not raw:
            return {}
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise HermesApiError("Unexpected Hermes API response shape")
        return parsed

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def create_response(
        self,
        *,
        conversation: str,
        input_text: str,
        previous_response_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> HermesReply:
        payload = self._build_response_payload(
            conversation=conversation,
            input_text=input_text,
            previous_response_id=previous_response_id,
            metadata=metadata,
        )
        response = self._request("POST", "/responses", payload)
        return HermesReply(
            text=self._extract_text(response),
            response_id=response.get("id"),
            conversation=conversation,
            raw_response=response,
        )

    def create_response_stream(
        self,
        *,
        conversation: str,
        input_text: str,
        previous_response_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        on_text_delta: Callable[[str], None] | None = None,
        on_tool_event: Callable[[str], None] | None = None,
    ) -> HermesReply:
        payload = self._build_response_payload(
            conversation=conversation,
            input_text=input_text,
            previous_response_id=previous_response_id,
            metadata=metadata,
        )
        payload["stream"] = True
        url = f"{self.config.hermes_api_base.rstrip('/')}/responses"
        headers = {"Authorization": f"Bearer {self.config.hermes_api_key}"}
        response_payload: dict[str, Any] | None = None
        response_id: str | None = None
        text_chunks: list[str] = []
        with requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=self.config.request_timeout_seconds,
            stream=True,
        ) as response:
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                body = response.text
                if response.status_code in {400, 404, 405, 415, 422, 501}:
                    raise HermesStreamFallbackRequested(f"HTTP {response.status_code}: {body}") from exc
                raise HermesApiError(f"HTTP {response.status_code}: {body}") from exc
            content_type = response.headers.get("Content-Type", "")
            if "text/event-stream" not in content_type:
                raw = response.text
                parsed = json.loads(raw) if raw else {}
                return HermesReply(
                    text=self._extract_text(parsed),
                    response_id=parsed.get("id"),
                    conversation=conversation,
                    raw_response=parsed,
                )
            for raw_line in response.iter_lines(decode_unicode=True):
                line = (raw_line or "").strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data:
                    continue
                if data == "[DONE]":
                    break
                event = json.loads(data)
                if not isinstance(event, dict):
                    continue
                event_type = str(event.get("type") or "")
                if event_type == "response.output_text.delta":
                    delta = str(event.get("delta") or "")
                    if delta:
                        text_chunks.append(delta)
                        if on_text_delta:
                            on_text_delta(delta)
                    continue
                if event_type in {"response.output_item.added", "response.output_item.done"}:
                    tool_message = self._tool_event_message(event, done=event_type.endswith(".done"))
                    if tool_message and on_tool_event:
                        on_tool_event(tool_message)
                    continue
                if event_type == "response.failed":
                    error = event.get("error") or event.get("response") or event
                    raise HermesApiError(f"Hermes streamed response failed: {error}")
                if event_type == "response.completed":
                    maybe_response = event.get("response")
                    if isinstance(maybe_response, dict):
                        response_payload = maybe_response
                        response_id = maybe_response.get("id")
                    break
                if isinstance(event.get("response"), dict):
                    response_id = event["response"].get("id") or response_id
        if response_payload is None:
            response_payload = {"id": response_id, "output_text": "".join(text_chunks)}
        return HermesReply(
            text=("".join(text_chunks) or self._extract_text(response_payload)).strip(),
            response_id=response_payload.get("id"),
            conversation=conversation,
            raw_response=response_payload,
        )

    def _build_response_payload(
        self,
        *,
        conversation: str,
        input_text: str,
        previous_response_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.config.hermes_model,
            "input": input_text,
            "store": True,
            "instructions": (
                "You are replying to a DingTalk chat bridged into Hermes. "
                "Default to a short direct conversational reply in the user's language. "
                "Do not call tools, search files, read memory, or inspect the environment "
                "unless the user explicitly asks you to perform an action that truly requires tools."
            ),
        }
        if previous_response_id:
            payload["previous_response_id"] = previous_response_id
        else:
            payload["conversation"] = conversation
        if metadata and self.config.include_metadata_header:
            payload["metadata"] = metadata
        return payload

    @staticmethod
    def _tool_event_message(event: dict[str, Any], *, done: bool) -> str | None:
        item = event.get("item")
        if not isinstance(item, dict):
            return None
        item_type = str(item.get("type") or "").strip()
        if not item_type or item_type in {"message", "reasoning", "function_call_output"}:
            return None
        if item_type != "function_call" or done:
            return None
        name = str(item.get("name") or "function_call").strip()
        arguments = HermesClient._parse_tool_arguments(item.get("arguments"))
        preview = HermesClient._tool_argument_preview(name, arguments)
        emoji = HermesClient._tool_emoji(name)
        return f"{emoji} {name}: {preview}"

    @staticmethod
    def _parse_tool_arguments(raw_arguments: Any) -> dict[str, Any]:
        if isinstance(raw_arguments, dict):
            return raw_arguments
        if not raw_arguments:
            return {}
        try:
            parsed = json.loads(str(raw_arguments))
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _tool_argument_preview(name: str, arguments: dict[str, Any]) -> str:
        preferred_keys = {
            "skills_list": ["category", "query", "skill", "name"],
            "skill_view": ["skill_name", "name", "skill", "path"],
            "search_files": ["pattern", "query", "path"],
            "read_file": ["path"],
            "terminal": ["command", "cmd"],
            "search_web": ["query", "q"],
        }
        keys = preferred_keys.get(name, [])
        for key in keys:
            value = arguments.get(key)
            if value:
                return HermesClient._compact_preview(value)
        for key in ("query", "q", "pattern", "path", "command", "cmd", "name"):
            value = arguments.get(key)
            if value:
                return HermesClient._compact_preview(value)
        if arguments:
            return HermesClient._compact_preview(json.dumps(arguments, ensure_ascii=False))
        return '"..."'

    @staticmethod
    def _compact_preview(value: Any, *, limit: int = 72) -> str:
        if isinstance(value, (list, tuple)):
            text = " | ".join(str(item) for item in value)
        else:
            text = str(value)
        text = " ".join(text.split())
        if len(text) > limit:
            text = text[: limit - 3] + "..."
        return json.dumps(text, ensure_ascii=False)

    @staticmethod
    def _tool_emoji(name: str) -> str:
        if "skill" in name:
            return "📚"
        if name in {"terminal", "shell", "exec"}:
            return "💻"
        if name.startswith("search") or name.startswith("find"):
            return "🔎"
        if name.startswith("read"):
            return "📄"
        return "🛠"

    @staticmethod
    def _extract_text(response: dict[str, Any]) -> str:
        output = response.get("output")
        if isinstance(output, list):
            chunks: list[str] = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "message":
                    for content in item.get("content", []):
                        if isinstance(content, dict) and content.get("type") in {"output_text", "text"}:
                            text = content.get("text")
                            if text:
                                chunks.append(str(text))
                elif item.get("type") == "output_text":
                    text = item.get("text")
                    if text:
                        chunks.append(str(text))
            if chunks:
                return "\n".join(chunks).strip()
        if isinstance(response.get("output_text"), str):
            return str(response["output_text"]).strip()
        return ""

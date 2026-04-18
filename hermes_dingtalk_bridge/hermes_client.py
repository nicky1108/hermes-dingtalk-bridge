from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Optional

from .config import BridgeConfig
from .models import HermesReply


logger = logging.getLogger(__name__)


class HermesApiError(RuntimeError):
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
        response = self._request("POST", "/responses", payload)
        return HermesReply(
            text=self._extract_text(response),
            response_id=response.get("id"),
            conversation=conversation,
            raw_response=response,
        )

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

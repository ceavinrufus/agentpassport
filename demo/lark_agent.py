"""Lark APS agent — uses app credentials (LARK_APP_ID + LARK_APP_SECRET) or mock fallback.

Set env vars:
  LARK_APP_ID      — your Lark app ID (cli_xxx)
  LARK_APP_SECRET  — your Lark app secret
  LARK_CHAT_ID     — chat to send alerts to (optional)
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from aps_sdk import Agent, TaskEnvelope

lark_agent = Agent(name="lark-agent")

LARK_API = "https://open.larksuite.com/open-apis"


def _get_tenant_token() -> str | None:
    app_id = os.environ.get("LARK_APP_ID")
    app_secret = os.environ.get("LARK_APP_SECRET")
    if not app_id or not app_secret:
        return None
    payload = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
    req = urllib.request.Request(
        f"{LARK_API}/auth/v3/tenant_access_token/internal",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            data = json.loads(resp.read())
            return data.get("tenant_access_token")
    except Exception:  # noqa: BLE001
        return None


def _api_get(path: str, token: str) -> dict:
    req = urllib.request.Request(
        f"{LARK_API}{path}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
        return json.loads(resp.read())


def _api_post(path: str, token: str, body: dict) -> dict:
    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{LARK_API}{path}",
        data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
        return json.loads(resp.read())


@lark_agent.capability("notify_team")
async def notify_team(task: TaskEnvelope) -> dict[str, Any]:
    summary = task.intent.params.get("summary", "Incident detected.")
    incident_id = task.intent.params.get("incident_id", "unknown")
    chat_id = task.intent.params.get("chat_id") or os.environ.get("LARK_CHAT_ID")
    text = f"[APS Alert] {incident_id}: {summary}"

    token = _get_tenant_token()
    if not token:
        return {
            "source": "lark",
            "notified": False,
            "channel": "mock",
            "message": f"[MOCK] Would notify: {text}",
        }

    if not chat_id:
        return {
            "source": "lark",
            "notified": False,
            "channel": "app",
            "message": text,
            "note": "Authenticated. Set LARK_CHAT_ID to send messages.",
        }

    try:
        resp = _api_post(
            "/im/v1/messages?receive_id_type=chat_id",
            token,
            {
                "receive_id": chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}),
            },
        )
        return {
            "source": "lark",
            "notified": resp.get("code", -1) == 0,
            "channel": "app",
            "message": text,
        }
    except Exception as e:  # noqa: BLE001
        return {"source": "lark", "notified": False, "channel": "app", "error": str(e)}


@lark_agent.capability("read_document")
async def read_document(task: TaskEnvelope) -> dict[str, Any]:
    doc_id = task.intent.params.get("document_id")
    if not doc_id:
        return {"source": "lark", "error": "document_id required"}

    token = _get_tenant_token()
    if not token:
        return {"source": "lark", "error": "LARK_APP_ID + LARK_APP_SECRET required"}

    try:
        data = _api_get(f"/docx/v1/documents/{doc_id}/raw_content", token)
        return {"source": "lark", "document_id": doc_id, "content": data.get("data", {})}
    except urllib.error.HTTPError as e:
        return {"source": "lark", "error": f"HTTP {e.code}: {e.reason}"}

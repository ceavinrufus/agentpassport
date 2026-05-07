"""Lark APS agent — notifies team and reads docs via app credentials or webhook fallback.

Auth modes (in priority order):
  1. LARK_APP_ID + LARK_APP_SECRET  — full API access (send messages, read docs/wiki/base)
  2. LARK_WEBHOOK_URL               — outbound-only (send messages only)
  3. Neither set                    — mock fallback
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
    """Exchange app credentials for a tenant access token."""
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


def _lark_get(path: str, token: str) -> dict:
    req = urllib.request.Request(
        f"{LARK_API}{path}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
        return json.loads(resp.read())


def _lark_post(path: str, token: str, body: dict) -> dict:
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
    # Optional: send to a specific chat (open_id or chat_id)
    chat_id = task.intent.params.get("chat_id") or os.environ.get("LARK_CHAT_ID")

    text = f"[APS Alert] {incident_id}: {summary}"

    # --- Mode 1: App credentials (full API) ---
    token = _get_tenant_token()
    if token:
        try:
            receive_id = chat_id or os.environ.get("LARK_CHAT_ID")
            if receive_id:
                resp = _lark_post(
                    "/im/v1/messages?receive_id_type=chat_id",
                    token,
                    {
                        "receive_id": receive_id,
                        "msg_type": "text",
                        "content": json.dumps({"text": text}),
                    },
                )
                notified = resp.get("code", -1) == 0
            else:
                # No chat_id — token is valid but nowhere to send; still report as app-authed
                notified = False
            return {
                "source": "lark",
                "notified": notified,
                "channel": "app",
                "message": text,
                "note": "Authenticated via LARK_APP_ID. Set LARK_CHAT_ID to send messages.",
            }
        except Exception:  # noqa: BLE001
            pass  # fall through to webhook

    # --- Mode 2: Webhook (outbound only) ---
    webhook_url = os.environ.get("LARK_WEBHOOK_URL")
    if webhook_url:
        try:
            payload = json.dumps({"msg_type": "text", "content": {"text": text}}).encode()
            req = urllib.request.Request(
                webhook_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
                notified = resp.status == 200
        except Exception:  # noqa: BLE001
            notified = False
        return {"source": "lark", "notified": notified, "channel": "webhook", "message": text}

    # --- Mode 3: Mock ---
    return {
        "source": "lark",
        "notified": False,
        "channel": "mock",
        "message": f"[MOCK] Would notify team about {incident_id}: {summary}",
    }


@lark_agent.capability("read_document")
async def read_document(task: TaskEnvelope) -> dict[str, Any]:
    """Read a Lark document by document_id. Requires app credentials."""
    doc_id = task.intent.params.get("document_id")
    if not doc_id:
        return {"source": "lark", "error": "document_id required"}

    token = _get_tenant_token()
    if not token:
        return {
            "source": "lark",
            "error": "LARK_APP_ID + LARK_APP_SECRET required to read documents (webhook cannot read)",
        }

    try:
        data = _lark_get(f"/docx/v1/documents/{doc_id}/raw_content", token)
        return {"source": "lark", "document_id": doc_id, "content": data.get("data", {})}
    except urllib.error.HTTPError as e:
        return {"source": "lark", "error": f"HTTP {e.code}: {e.reason}"}

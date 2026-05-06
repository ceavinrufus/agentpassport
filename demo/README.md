# APS Incident Investigation Demo

A 3-agent demo showing the Agent Protocol Stack (APS) in action.

## What it shows

- **Orchestrator** coordinates two sub-agents in-process for incident investigation
- **Datadog agent** queries metrics via `pup` CLI; falls back to mock when unauthenticated
- **Lark agent** posts alerts to a Lark webhook; falls back to mock when env vars are absent

Works out-of-the-box with mock fallbacks — no credentials required.

## How to run

```bash
uv run python -m demo.run_demo
```

## Optional: real data sources

**Datadog** — authenticate with `pup auth login`, then the agent calls `pup metrics query`.

**Lark** — set `LARK_WEBHOOK_URL` (or `LARK_APP_ID` + `LARK_APP_SECRET`):
```bash
export LARK_WEBHOOK_URL=https://open.larksuite.com/open-apis/bot/v2/hook/<token>
```

## Mock fallbacks

Without credentials, Datadog returns sample CPU metrics and Lark logs what it would have sent.

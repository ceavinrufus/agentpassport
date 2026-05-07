# APS Incident Investigation Demo

A 3-agent demo showing the Agent Protocol Stack (APS) in action.

## What it shows

- **Orchestrator** coordinates two sub-agents in-process for incident investigation
- **Datadog agent** queries metrics via `pup` CLI; falls back to mock when unauthenticated
- **Lark agent** sends notifications and reads documents; falls back to mock when unconfigured

Works out-of-the-box with mock fallbacks — no credentials required.

## How to run

```bash
uv run python -m demo.run_demo
```

## Optional: real data sources

### Datadog
Authenticate with `pup auth login`, then the agent calls `pup metrics query`.

### Lark — app credentials (recommended)
Gives full API access: send messages **and** read documents/wiki/base.
```bash
export LARK_APP_ID=cli_xxx
export LARK_APP_SECRET=xxx
export LARK_CHAT_ID=oc_xxx   # optional: chat to send alerts to
```

### Lark — webhook (outbound only)
Can only send messages, cannot read documents.
```bash
export LARK_WEBHOOK_URL=https://open.larksuite.com/open-apis/bot/v2/hook/<token>
```

## Mock fallbacks

Without credentials, Datadog returns sample CPU metrics and Lark logs what it would have sent.

# APS Incident Investigation Demo

A 3-agent demo showing the Agent Protocol Stack (APS) in action.

## What it shows

- **Orchestrator** coordinates two sub-agents in-process for incident investigation
- **Datadog agent** queries metrics via `pup` CLI; falls back to mock when unauthenticated
- **Lark agent** sends notifications and reads documents via app credentials; falls back to mock

Works out-of-the-box with mock fallbacks — no credentials required.

## How to run

```bash
# Install deps (first time only)
cd packages/aps-sdk-ts && npm install && cd ../..
cd demo/ts_agent && npm install && cd ../..

# Run the demo
uv run python -m demo.run_demo
```

## Optional: real data sources

### Datadog
```bash
pup auth login
```

### Lark
```bash
export LARK_APP_ID=cli_xxx
export LARK_APP_SECRET=xxx
export LARK_CHAT_ID=oc_xxx   # optional: chat to send alerts to
```

## Mock fallbacks

Without credentials, Datadog returns sample CPU metrics and Lark logs what it would have sent.

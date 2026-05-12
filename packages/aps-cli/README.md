# aps-cli — CLI Tools

Command-line tools for APS — identity management and trace inspection.

## Install

```bash
pip install agentps-cli
```

## Commands

### Identity

```bash
# Generate a keypair and DID
aps identity keygen --alias myagent

# Show a stored DID
aps identity show --alias myagent
```

### Trace

```bash
# Render a trace with full auth chain verification
aps trace show --id trace_abc123 --file traces.jsonl

# JSON output
aps trace show --id trace_abc123 --file traces.jsonl --json-output
```

The trace viewer renders each task's auth chain — issuer → subject, scope, expiry, and ✅/❌ signature verification against the DID's embedded public key.

## Development

```bash
uv sync --all-packages
uv run pytest tests/cli/
```

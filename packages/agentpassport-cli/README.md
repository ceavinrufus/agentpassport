# agentpassport-cli — CLI Tools

Command-line tools for agentpassport — identity management and trace inspection.

## Install

```bash
pip install agentpassport-cli
```

## Commands

### Identity

```bash
# Generate a keypair and DID
agentpassport identity keygen --alias myagent

# Show a stored DID
agentpassport identity show --alias myagent
```

### Trace

```bash
# Render a trace with full auth chain verification
agentpassport trace show --id trace_abc123 --file traces.jsonl

# JSON output
agentpassport trace show --id trace_abc123 --file traces.jsonl --json-output
```

The trace viewer renders each task's auth chain — issuer → subject, scope, expiry, and ✅/❌ signature verification against the DID's embedded public key.

## Development

```bash
uv sync --all-packages
uv run pytest tests/cli/
```

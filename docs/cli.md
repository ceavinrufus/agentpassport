# CLI Reference

`agentpassport-cli` provides command-line tools for managing agent identities, ownership bindings, and task traces.

## Installation

```bash
pip install agentpassport-cli
```

## Aliases

The CLI is available under three aliases — all are equivalent:

```
agentpassport
agentpass
ap
```

## Usage

```
agentpass [OPTIONS] COMMAND [ARGS]...
```

**Options:**

| Flag | Description |
|------|-------------|
| `--version` | Show the installed version and exit |
| `--help` | Show help and exit |

---

## `identity` — Manage DIDs and Bindings

```
agentpass identity COMMAND [ARGS]...
```

Manage agentpassport identities (DIDs, keypairs, and ownership bindings).

---

### `identity keygen`

Generate a new Ed25519 keypair and DID, stored in the local keystore.

```
agentpass identity keygen --alias ALIAS [--keystore PATH]
```

**Flags:**

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--alias` | yes | — | Name for the keypair |
| `--keystore` | no | `~/.agentpassport/keystore.json` | Path to keystore file |

**Example:**

```
agentpass identity keygen --alias myagent
```

**Output:**

```
✓ Generated DID: did:key:z6Mkh8UwkN88kwynM3mYke8yFXr9ax69jZKv2TCuwG7yPzbw
  Alias: myagent
  Keystore: /home/user/.agentpassport/keystore.json
```

---

### `identity list`

List all keypairs stored in the keystore.

```
agentpass identity list [--keystore PATH]
```

**Flags:**

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--keystore` | no | `~/.agentpassport/keystore.json` | Path to keystore file |

**Example:**

```
agentpass identity list
```

**Output:**

```
  myagent: did:key:z6Mkh8UwkN88kwynM3mYke8yFXr9ax69jZKv2TCuwG7yPzbw
  worker:  did:key:z6MkpTHR8VNsBxYAAWHut2Geadd9jSwuias8sitwHTi1KGmW
```

---

### `identity bind-domain`

Create a signed domain ownership binding and write it to a JSON file for publishing.

```
agentpass identity bind-domain \
  --alias ALIAS \
  --domain DOMAIN \
  [--keystore PATH] \
  [--output FILE] \
  [--expires-at UNIX_TS] \
  [--yes]
```

**Flags:**

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--alias` | yes | — | Alias of the keypair to sign with |
| `--domain` | yes | — | Domain to bind (e.g. `example.com`) — scheme and path are stripped automatically |
| `--keystore` | no | `~/.agentpassport/keystore.json` | Path to keystore file |
| `--output` | no | `agent-passport.json` | Output file path |
| `--expires-at` | no | — | Optional expiry as a Unix timestamp |
| `--yes`, `-y` | no | — | Skip confirmation prompt |

After generating the file, publish it at `https://{domain}/.well-known/agent-passport.json`.

**Example:**

```
agentpass identity bind-domain \
  --alias myagent \
  --domain agentpassport.fyi \
  --output agent-passport.json \
  --yes
```

**Output:**

```
  DID:    did:key:z6Mkh8UwkN88kwynM3mYke8yFXr9ax69jZKv2TCuwG7yPzbw
  Domain: agentpassport.fyi
  Output: agent-passport.json

✓ Domain binding created for 'agentpassport.fyi'

  Publish the output file at:
  https://agentpassport.fyi/.well-known/agent-passport.json
```

---

### `identity bind-wallet`

Create a signed wallet ownership binding.

```
agentpass identity bind-wallet \
  --alias ALIAS \
  --chain CHAIN \
  --address ADDRESS \
  [--keystore PATH] \
  [--output FILE] \
  [--expires-at UNIX_TS] \
  [--yes]
```

**Flags:**

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--alias` | yes | — | Alias of the keypair to sign with |
| `--chain` | yes | — | Chain identifier (e.g. `ethereum`, `solana`, `bitcoin`) |
| `--address` | yes | — | Wallet address |
| `--keystore` | no | `~/.agentpassport/keystore.json` | Path to keystore file |
| `--output` | no | `agent-passport.json` | Output file path |
| `--expires-at` | no | — | Optional expiry as a Unix timestamp |
| `--yes`, `-y` | no | — | Skip confirmation prompt |

!!! warning
    Double-check the wallet address before confirming — wallet bindings cannot be auto-corrected.

**Example:**

```
agentpass identity bind-wallet \
  --alias myagent \
  --chain ethereum \
  --address 0xAbCd1234... \
  --yes
```

**Output:**

```
  DID:     did:key:z6Mkh8UwkN88kwynM3mYke8yFXr9ax69jZKv2TCuwG7yPzbw
  Chain:   ethereum
  Address: 0xAbCd1234...
  Output:  agent-passport.json

  ⚠️  Double-check the address — wallet bindings cannot be auto-corrected.

✓ Wallet binding created for ethereum:0xAbCd1234...
```

---

### `identity revoke-wallet`

Add a signed revocation for a wallet binding to the binding document.

```
agentpass identity revoke-wallet \
  --alias ALIAS \
  --chain CHAIN \
  --address ADDRESS \
  [--keystore PATH] \
  [--output FILE] \
  [--yes]
```

**Flags:**

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--alias` | yes | — | Alias of the keypair that created the original binding |
| `--chain` | yes | — | Chain identifier |
| `--address` | yes | — | Wallet address to revoke |
| `--keystore` | no | `~/.agentpassport/keystore.json` | Path to keystore file |
| `--output` | no | `agent-passport.json` | Binding document to update |
| `--yes`, `-y` | no | — | Skip confirmation prompt |

After running, republish the updated file to make the revocation effective.

**Example:**

```
agentpass identity revoke-wallet \
  --alias myagent \
  --chain ethereum \
  --address 0xAbCd1234... \
  --yes
```

**Output:**

```
  DID:     did:key:z6Mkh8UwkN88kwynM3mYke8yFXr9ax69jZKv2TCuwG7yPzbw
  Chain:   ethereum
  Address: 0xAbCd1234...
  Output:  agent-passport.json

✓ Wallet binding revoked for ethereum:0xAbCd1234...

  Republish the updated file to take effect.
```

---

### `identity verify-domain`

Verify that a domain's published binding document claims ownership of an agent DID.

Fetches `https://{domain}/.well-known/agent-passport.json` and checks the signature.

```
agentpass identity verify-domain \
  --did DID \
  --domain DOMAIN \
  [--timeout SECONDS]
```

**Flags:**

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--did` | yes | — | Agent DID to verify |
| `--domain` | yes | — | Domain hosting the binding document |
| `--timeout` | no | `5.0` | HTTP request timeout in seconds |

**Example (live demo):**

```
agentpass identity verify-domain \
  --did did:key:z6Mkh8UwkN88kwynM3mYke8yFXr9ax69jZKv2TCuwG7yPzbw \
  --domain agentpassport.fyi

Checking https://agentpassport.fyi/.well-known/agent-passport.json ...
✓ Valid domain binding: 'agentpassport.fyi' claims did:key:z6Mkh8UwkN88kwynM3mYke8yFXr9ax69jZKv2TCuwG7yPzbw
```

Exits with status code `1` if verification fails.

---

### `identity verify-wallet`

Verify that a wallet address is bound to an agent DID via a domain's published binding document.

Fetches `https://{domain}/.well-known/agent-passport.json` and checks the signature.

```
agentpass identity verify-wallet \
  --did DID \
  --chain CHAIN \
  --address ADDRESS \
  --domain DOMAIN \
  [--timeout SECONDS]
```

**Flags:**

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--did` | yes | — | Agent DID to verify |
| `--chain` | yes | — | Chain identifier |
| `--address` | yes | — | Wallet address |
| `--domain` | yes | — | Domain hosting the binding document |
| `--timeout` | no | `5.0` | HTTP request timeout in seconds |

**Example:**

```
agentpass identity verify-wallet \
  --did did:key:z6Mkh8UwkN88kwynM3mYke8yFXr9ax69jZKv2TCuwG7yPzbw \
  --chain ethereum \
  --address 0xAbCd1234... \
  --domain agentpassport.fyi

Checking https://agentpassport.fyi/.well-known/agent-passport.json ...
✓ Valid wallet binding: ethereum:0xAbCd1234... → did:key:z6Mkh8UwkN88kwynM3mYke8yFXr9ax69jZKv2TCuwG7yPzbw
```

Exits with status code `1` if verification fails.

---

### `identity list-bindings`

List all bindings and revocations in a local binding document.

```
agentpass identity list-bindings [--output FILE]
```

**Flags:**

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--output` | no | `agent-passport.json` | Binding document to inspect |

**Example:**

```
agentpass identity list-bindings --output agent-passport.json
```

**Output:**

```
Bindings (2):
  [domain]
    did:     did:key:z6Mkh8UwkN88kwynM3mYke8yFXr9ax69jZKv2TCuwG7yPzbw
    claim:   {'domain': 'agentpassport.fyi'}
    issued:  1715000000
  [wallet]
    did:     did:key:z6Mkh8UwkN88kwynM3mYke8yFXr9ax69jZKv2TCuwG7yPzbw
    claim:   {'chain': 'ethereum', 'address': '0xAbCd1234...'}
    issued:  1715001000

Revocations (0):
```

Bindings that have been revoked are shown with a `[REVOKED]` marker. Expired bindings are shown with an `[EXPIRED]` marker.

---

### `identity remove-binding`

Remove a specific binding entry from a local binding document (useful for fixing typos or removing stale entries). Does not issue a cryptographic revocation — use `revoke-wallet` for that.

```
agentpass identity remove-binding \
  --type {domain|wallet} \
  [--domain DOMAIN] \
  [--chain CHAIN] \
  [--address ADDRESS] \
  [--output FILE] \
  [--yes]
```

**Flags:**

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--type` | yes | — | Binding type: `domain` or `wallet` |
| `--domain` | conditional | — | Required when `--type domain` |
| `--chain` | conditional | — | Required when `--type wallet` |
| `--address` | conditional | — | Required when `--type wallet` |
| `--output` | no | `agent-passport.json` | Binding document to modify |
| `--yes`, `-y` | no | — | Skip confirmation prompt |

**Example — remove a domain binding:**

```
agentpass identity remove-binding \
  --type domain \
  --domain agentpassport.fyi \
  --yes
```

**Output:**

```
  Found 1 matching binding(s):
    - type=domain, claim={'domain': 'agentpassport.fyi'}, issued_at=1715000000

✓ Removed 1 binding(s) from 'agent-passport.json'
```

**Example — remove a wallet binding:**

```
agentpass identity remove-binding \
  --type wallet \
  --chain ethereum \
  --address 0xAbCd1234... \
  --yes
```

---

## `trace` — View Task Execution Traces

```
agentpass trace COMMAND [ARGS]...
```

View and analyze task execution traces, including auth chain verification for each task.

---

### `trace show`

Display a trace tree with auth chain details for each task.

By default, reads from `~/.agentpassport/traces.jsonl`. Use `--file` to specify a different log file.

```
agentpass trace show --id TRACE_ID [--file PATH] [--json-output]
```

**Flags:**

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--id` | yes | — | Trace ID to display |
| `--file` | no | `~/.agentpassport/traces.jsonl` | Log file to read events from |
| `--json-output` | no | — | Output raw JSON (one event per line) instead of the tree view |

**Example:**

```
agentpass trace show --id trace-abc123
```

**Output (tree view):**

```
trace trace-abc123
└── task-001  agent: did:key:z6Mkh8…yPzbw  → completed
    ├── task_started
    ├── task_completed  cost=0.0012
    └── auth chain
        ├── ✓ hop 1  jti=a1b2c3d4…
        │   ├── iss did:key:z6Mkh8…yPzbw
        │   ├── sub did:key:z6MkpT…KGmW
        │   ├── scope read, write
        │   └── exp 2025-06-01T00:00:00Z
        └── ✓ hop 2  jti=e5f6g7h8…
            ├── iss did:key:z6MkpT…KGmW
            ├── sub did:key:z6Mkr9…xQfA
            ├── scope read
            └── exp 2025-06-01T00:00:00Z
```

**Example — raw JSON output:**

```
agentpass trace show --id trace-abc123 --json-output
```

Outputs one `ObservabilityEvent` JSON object per line, suitable for piping to `jq` or other tools.

**Example — custom log file:**

```
agentpass trace show --id trace-abc123 --file /var/log/agent/traces.jsonl
```

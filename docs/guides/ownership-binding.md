# Guide: Agent Identity & Ownership Binding

This guide covers how to give your agent a verifiable real-world identity — linking its DID to a domain you control or a blockchain wallet you own.

By the end you'll know how to:
1. Generate an agent identity (DID + keypair)
2. Bind your agent to a domain
3. Bind your agent to a wallet address
4. Publish the binding document
5. Verify bindings (offline and online)
6. Revoke a wallet binding
7. Fix mistakes with `remove-binding`
8. Use the Python API directly (without the CLI)

---

## The problem

An agent's DID (`did:key:z6Mk...`) proves cryptographic ownership of a key — but it doesn't tell you who *controls* that key in the real world. Anyone can generate a DID and claim to be anyone.

Ownership binding creates a cryptographic link between an agent DID and something you publicly control:

- **Domain binding** — `rufus.dev` hosts a signed file proving it owns `did:key:z6Mk...`
- **Wallet binding** — a signed attestation proves `0x1234...` on Ethereum is linked to `did:key:z6Mk...`

Both bindings are signed by the agent's private key. No central registry. No chain calls. Just crypto + DNS.

---

## Prerequisites

```bash
pip install agentpassport agentpassport-cli
```

---

## Step 1: Generate an agent identity

```bash
agentpass identity keygen --alias myagent
```

```
✓ Generated DID: did:key:z6MkskpV...
  Alias: myagent
  Keystore: /root/.agentpassport/keys.json
```

Your keypair is stored at `~/.agentpassport/keys.json` with `0o600` permissions (owner read/write only). Treat this file like an SSH private key.

List your identities at any time:

```bash
agentpass identity list
```

---

## Step 2: Create a domain binding

```bash
agentpass identity bind-domain \
  --alias myagent \
  --domain rufus.dev \
  --output agent-passport.json
```

The CLI will show you exactly what it's about to create and ask for confirmation:

```
  DID:    did:key:z6MkskpV...
  Domain: rufus.dev
  Output: agent-passport.json

Create this domain binding? [y/N]: y
✓ Domain binding created for 'rufus.dev'

  Publish the output file at:
  https://rufus.dev/.well-known/agent-passport.json
```

The output file (`agent-passport.json`) looks like:

```json
{
  "version": "1",
  "bindings": [
    {
      "type": "domain",
      "agent_did": "did:key:z6MkskpV...",
      "claim": {
        "domain": "rufus.dev"
      },
      "issued_at": 1778716471,
      "expires_at": null,
      "signature": "<ed25519 hex>"
    }
  ],
  "revocations": []
}
```

### Optional: set an expiry

```bash
agentpass identity bind-domain \
  --alias myagent \
  --domain rufus.dev \
  --expires-at 1810252471 \
  --output agent-passport.json \
  --yes
```

Use `--yes` / `-y` to skip the confirmation prompt (useful in scripts).

### Binding strips common mistakes automatically

The CLI is lenient about domain input:

| Input | Cleaned to |
|-------|-----------|
| `https://rufus.dev` | `rufus.dev` |
| `rufus.dev/some/path` | `rufus.dev` |
| `Rufus.DEV` | `rufus.dev` |

Ports are rejected: `rufus.dev:8080` → error.

---

## Step 3: Publish the binding document

Upload `agent-passport.json` to your web server so it's accessible at:

```
https://rufus.dev/.well-known/agent-passport.json
```

**nginx:**
```nginx
location /.well-known/agent-passport.json {
    alias /var/www/.well-known/agent-passport.json;
    default_type application/json;
}
```

**Vercel / Next.js:** put it in `public/.well-known/agent-passport.json`.

**GitHub Pages:** put it in `.well-known/agent-passport.json` at the repo root.

The file must:
- Be served over HTTPS
- Return `Content-Type: application/json` (or any JSON-compatible type)
- Be publicly accessible without auth

---

## Step 4: Add a wallet binding

You can add multiple bindings — domain and wallet — to the same file:

```bash
agentpass identity bind-wallet \
  --alias myagent \
  --chain ethereum \
  --address 0xYourWalletAddress \
  --output agent-passport.json
```

```
  DID:     did:key:z6MkskpV...
  Chain:   ethereum
  Address: 0xYourWalletAddress
  Output:  agent-passport.json

  ⚠️  Double-check the address — wallet bindings cannot be auto-corrected.

Create this wallet binding? [y/N]: y
✓ Wallet binding created for ethereum:0xYourWalletAddress
```

The document now contains both bindings:

```json
{
  "version": "1",
  "bindings": [
    {
      "type": "domain",
      "agent_did": "did:key:z6Mk...",
      "claim": { "domain": "rufus.dev" },
      "issued_at": 1778716471,
      "expires_at": null,
      "signature": "..."
    },
    {
      "type": "wallet",
      "agent_did": "did:key:z6Mk...",
      "claim": { "chain": "ethereum", "address": "0xYourWalletAddress" },
      "issued_at": 1778716480,
      "expires_at": null,
      "signature": "..."
    }
  ],
  "revocations": []
}
```

### Supported chains

| Chain | Validation |
|-------|-----------|
| `ethereum`, `base`, `polygon`, `optimism`, `arbitrum`, `avalanche`, `bnb`, `gnosis`, `zksync`, `linea` | `0x` + 40 hex chars |
| `solana` | Base58, 32–44 chars |
| `bitcoin` | `1...`, `3...`, or `bc1...` |
| anything else | Passes through — format not validated |

Republish the updated file after adding wallet bindings.

---

## Step 5: Verify bindings

### From the CLI

```bash
# Verify domain binding (fetches from network)
agentpass identity verify-domain \
  --did did:key:z6MkskpV... \
  --domain rufus.dev
```

```
  Checking https://rufus.dev/.well-known/agent-passport.json ...
✓ Valid domain binding: 'rufus.dev' claims did:key:z6MkskpV...
```

```bash
# Verify wallet binding
agentpass identity verify-wallet \
  --did did:key:z6MkskpV... \
  --chain ethereum \
  --address 0xYourWalletAddress \
  --domain rufus.dev
```

```
  Checking https://rufus.dev/.well-known/agent-passport.json ...
✓ Valid wallet binding: ethereum:0xYourWalletAddress → did:key:z6MkskpV...
```

Exit code is `0` on success, `1` on failure — suitable for shell scripts.

### Inspect the local document

```bash
agentpass identity list-bindings --output agent-passport.json
```

```
Bindings (2):
  [domain]
    did:     did:key:z6MkskpV...
    claim:   {'domain': 'rufus.dev'}
    issued:  1778716471
  [wallet]
    did:     did:key:z6MkskpV...
    claim:   {'chain': 'ethereum', 'address': '0xYour...'}
    issued:  1778716480
```

Shows `[REVOKED]` and `[EXPIRED]` status badges automatically.

### From Python

```python
from agentpassport import verify_domain_binding, verify_wallet_binding

# Online verification (fetches from network)
ok = verify_domain_binding("did:key:z6Mk...", "rufus.dev")
print(ok)  # True / False

ok = verify_wallet_binding("did:key:z6Mk...", "ethereum", "0xYour...", "rufus.dev")
print(ok)  # True / False
```

Offline verification (no network — verify a binding you have in hand):

```python
from agentpassport import verify_binding_attestation, Binding

binding = Binding(
    type="domain",
    agent_did="did:key:z6Mk...",
    claim={"domain": "rufus.dev"},
    issued_at=1778716471,
    expires_at=None,
    signature_hex="<hex>",
)
ok = verify_binding_attestation(binding)
```

---

## Step 6: Revoke a wallet binding

Domain binding is revoked by removing the entry from the document (see [Step 7](#step-7-fix-mistakes-with-remove-binding)).

Wallet bindings use explicit revocation — a signed attestation that says "this wallet is no longer linked to this DID":

```bash
agentpass identity revoke-wallet \
  --alias myagent \
  --chain ethereum \
  --address 0xYourWalletAddress \
  --output agent-passport.json
```

```
  DID:     did:key:z6MkskpV...
  Chain:   ethereum
  Address: 0xYourWalletAddress
  Output:  agent-passport.json

⚠️  Revoke this wallet binding? This cannot be undone without re-binding. [y/N]: y
✓ Wallet binding revoked for ethereum:0xYourWalletAddress

  Republish the updated file to take effect.
```

The document now has a `revocations` entry:

```json
{
  "version": "1",
  "bindings": [...],
  "revocations": [
    {
      "type": "wallet",
      "agent_did": "did:key:z6Mk...",
      "claim": { "chain": "ethereum", "address": "0xYourWalletAddress" },
      "revoked_at": 1778716999,
      "signature": "..."
    }
  ]
}
```

Republish the file. Any verifier fetching the document will see the revocation and reject the binding.

To re-bind the same wallet later, run `bind-wallet` again — a new binding entry is added; the old revocation stays but the new binding supersedes it.

---

## Step 7: Fix mistakes with `remove-binding`

Typed the wrong domain? Wrong wallet address? Use `remove-binding`:

```bash
# Remove a domain binding
agentpass identity remove-binding \
  --type domain \
  --domain rufus.dv \
  --output agent-passport.json

# Remove a wallet binding
agentpass identity remove-binding \
  --type wallet \
  --chain ethereum \
  --address 0xWrongAddress \
  --output agent-passport.json
```

```
  Found 1 matching binding(s):
    - type=domain, claim={'domain': 'rufus.dv'}, issued_at=1778716471

Remove these bindings? [y/N]: y
✓ Removed 1 binding(s) from 'agent-passport.json'
```

Then republish the corrected file.

---

## Step 8: Using the Python API directly

No CLI required — all operations are available as Python functions.

### Create bindings

```python
from agentpassport import (
    generate_keypair,
    did_from_public_key,
    bind_domain,
    bind_wallet,
    revoke_wallet,
    BindingDocument,
)

# Generate identity
priv, pub = generate_keypair()
did = did_from_public_key(pub)

# Create bindings
domain_binding = bind_domain(priv[:32], did, "rufus.dev")
wallet_binding = bind_wallet(priv[:32], did, "ethereum", "0xYourAddress")

# Assemble document
doc = BindingDocument(version="1")
doc.add(domain_binding)
doc.add(wallet_binding)

# Publish this JSON at /.well-known/agent-passport.json
print(doc.to_json())
```

### With expiry

```python
import time

# Expires in 1 year
one_year = int(time.time()) + 365 * 24 * 3600

binding = bind_domain(priv[:32], did, "rufus.dev", expires_at=one_year)
```

### Revoke

```python
from agentpassport import revoke_wallet

revocation = revoke_wallet(priv[:32], did, "ethereum", "0xYourAddress")
doc.revoke(revocation)

# Republish doc.to_json()
```

### Verify offline

```python
from agentpassport import verify_binding_attestation

ok = verify_binding_attestation(binding)  # checks signature + expiry, no network
```

### Verify online

```python
from agentpassport import verify_domain_binding, verify_wallet_binding

ok = verify_domain_binding(did, "rufus.dev", timeout=5.0)
ok = verify_wallet_binding(did, "ethereum", "0xYourAddress", "rufus.dev", timeout=5.0)
```

---

## Reference: Full CLI command list

```bash
agentpass identity keygen         --alias <name>
agentpass identity list
agentpass identity bind-domain    --alias <name> --domain <domain> --output <file> [--expires-at <ts>] [-y]
agentpass identity bind-wallet    --alias <name> --chain <chain> --address <addr> --output <file> [--expires-at <ts>] [-y]
agentpass identity revoke-wallet  --alias <name> --chain <chain> --address <addr> --output <file> [-y]
agentpass identity remove-binding --type <domain|wallet> [--domain <d>] [--chain <c>] [--address <a>] --output <file> [-y]
agentpass identity list-bindings  --output <file>
agentpass identity verify-domain  --did <did> --domain <domain> [--timeout <secs>]
agentpass identity verify-wallet  --did <did> --chain <chain> --address <addr> --domain <domain> [--timeout <secs>]
```

---

## FAQ

**Q: Does this require publishing to a blockchain?**
No. Everything is off-chain — a JSON file hosted on your domain. Blockchain integration is planned as an optional future extension.

**Q: Can I have multiple agents bound to the same domain?**
The document is an array, so yes — multiple `agent_did` values can appear in the same file. Verifiers filter by `agent_did`.

**Q: What if my domain doesn't support HTTPS?**
HTTPS is required. The verifier always fetches `https://`. Use Let's Encrypt if needed.

**Q: Can I bind the same wallet to multiple DIDs?**
Yes. Each agent maintains its own binding document. There's no global uniqueness constraint on wallet addresses.

**Q: What happens if I lose my private key?**
You can no longer create new bindings or revocations for that DID. Remove the document from `/.well-known/` to prevent stale bindings from being verified. Then generate a new identity with `keygen`.

**Q: Is the keystore encrypted?**
Not yet — keys are stored as plaintext hex. The file permissions are set to `0o600` (owner-only read/write). Full keychain integration is planned. For now, treat `~/.agentpassport/keys.json` like an SSH private key.

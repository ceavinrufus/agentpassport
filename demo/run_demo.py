"""
demo/run_demo.py — agentpassport Cross-SDK Trust Demo

Scenario:
  1. Python orchestrator creates identity, signs delegation JWT for TS agent
  2. TS agent receives TaskEnvelope, verifies auth chain, executes queryCustomers
  3. TS agent rejects writeCustomer — scope not granted (ScopeError)
  4. Python revokes the delegation JWT mid-scenario — TS agent soft-stops
  5. CLI-style auth chain trace rendered inline

Run with:
    uv run python -m demo.run_demo
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure the Python SDK is importable
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "packages" / "agentpassport" / "src"))

from agentpassport.identity.did import generate_keypair, did_from_public_key
from agentpassport.identity.signing import sign_delegation, _decode_jwt_claims

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DEMO_DIR = Path(__file__).parent
TS_AGENT_DIR = DEMO_DIR / "ts_agent"
BOOTSTRAP_PATH = DEMO_DIR / "bootstrap.json"
SERVER_JS = TS_AGENT_DIR / "server.js"
AGENT_PORT = 7700

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
W = 56

def rule():
    print("━" * W)

def header(text: str):
    rule()
    print(f"  {text}")
    rule()

def step(n: int, text: str):
    print(f"\n[STEP {n}] {text}")

def info(label: str, value: str):
    print(f"  {label:<12} {value}")

def ok(msg: str):
    print(f"  {msg} ✅")

def fail(msg: str):
    print(f"  {msg} ❌")

def arrow(direction: str, msg: str):
    sym = "→" if direction == "out" else "←"
    print(f"  {sym} {msg}")

def abbrev_did(did: str) -> str:
    # did:key:z6Mk<...> → z6Mk…<last4>
    suffix = did.split(":")[-1]
    return f"{suffix[:8]}…{suffix[-4:]}"

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
def http_post(url: str, body: dict) -> tuple[int, dict]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())

def http_get(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())

# ---------------------------------------------------------------------------
# Build the TS agent bundle
# ---------------------------------------------------------------------------
def npm_install_if_needed(directory: Path, label: str) -> None:
    if not (directory / "node_modules").exists():
        print(f"  Installing {label} deps...")
        result = subprocess.run(
            ["npm", "install"],
            cwd=directory,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(result.stderr)
            raise RuntimeError(f"npm install failed in {label}")

def build_ts_agent() -> None:
    print("\n[BUILD] Bundling TS agent...")
    sdk_dir = Path(__file__).parent.parent / "packages" / "agentpassport-ts"
    npm_install_if_needed(sdk_dir, "agentpassport-ts")
    npm_install_if_needed(TS_AGENT_DIR, "ts-agent")
    result = subprocess.run(
        ["npm", "run", "build:bundle"],
        cwd=TS_AGENT_DIR,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stderr)
        raise RuntimeError("Failed to build TS agent")
    print(f"  server.js written ({SERVER_JS.stat().st_size // 1024} KB)")

# ---------------------------------------------------------------------------
# Start the TS agent subprocess
# ---------------------------------------------------------------------------
def start_ts_agent() -> subprocess.Popen:
    proc = subprocess.Popen(
        ["node", str(SERVER_JS)],
        env={**os.environ, "AGENTPASSPORT_AGENT_PORT": str(AGENT_PORT)},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    # Wait for "AGENTPASSPORT_AGENT_READY" on stdout
    deadline = time.time() + 10
    while time.time() < deadline:
        line = proc.stdout.readline()  # type: ignore[union-attr]
        if "AGENTPASSPORT_AGENT_READY" in line:
            return proc
        if proc.poll() is not None:
            err = proc.stderr.read()  # type: ignore[union-attr]
            raise RuntimeError(f"TS agent exited early:\n{err}")
    raise RuntimeError("TS agent did not become ready in time")

# ---------------------------------------------------------------------------
# Auth chain trace renderer (Step 5)
# ---------------------------------------------------------------------------
def render_auth_chain(chain: list[str], known_keys: dict[str, bytes]) -> None:
    print()
    for i, token in enumerate(chain):
        try:
            claims = _decode_jwt_claims(token)
        except Exception as e:
            print(f"  hop {i}  [malformed: {e}]  ❌")
            continue

        iss = claims.get("iss", "?")
        sub = claims.get("sub", "?")
        jti = str(claims.get("jti", ""))
        scope = claims.get("scope", [])
        exp_ts = claims.get("exp", 0)
        exp_dt = datetime.fromtimestamp(float(exp_ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        now_ts = datetime.now(timezone.utc).timestamp()
        expired = float(exp_ts) < now_ts

        # Verify signature
        pub = known_keys.get(iss)
        if pub:
            try:
                from agentpassport.identity.signing import _verify_jwt_signature
                _verify_jwt_signature(token, pub)
                sig_ok = True
            except Exception:
                sig_ok = False
        else:
            sig_ok = False

        status = "✅" if (sig_ok and not expired) else "❌"
        jti_abbrev = jti[:8] + "…" if len(jti) > 8 else jti

        print(f"  hop {i}  jti={jti_abbrev}  {status}")
        print(f"    iss    {abbrev_did(iss)}")
        print(f"    sub    {abbrev_did(sub)}")
        print(f"    scope  {scope}")
        print(f"    exp    {exp_dt}{'  (EXPIRED)' if expired else ''}")

# ---------------------------------------------------------------------------
# Main demo
# ---------------------------------------------------------------------------
def main() -> None:
    header("agentpassport DEMO — Cross-SDK Trust Chain")

    # ------------------------------------------------------------------
    # Generate identities
    # ------------------------------------------------------------------
    orch_priv, orch_pub = generate_keypair()
    orch_did = did_from_public_key(orch_pub)

    agent_priv, agent_pub = generate_keypair()
    agent_did = did_from_public_key(agent_pub)

    print()
    info("Orchestrator", f"did:key:{abbrev_did(orch_did)}")
    info("TS Agent",     f"did:key:{abbrev_did(agent_did)}")

    # Write bootstrap for TS agent
    BOOTSTRAP_PATH.write_text(json.dumps({
        "orchestrator_did": orch_did,
        "orchestrator_public_key_hex": orch_pub.hex(),
        "agent_private_key_hex": agent_priv.hex(),
    }, indent=2))

    # ------------------------------------------------------------------
    # Build + start TS agent
    # ------------------------------------------------------------------
    build_ts_agent()
    print("\n[SERVER] Starting TS agent...")
    proc = start_ts_agent()
    print(f"  Listening on port {AGENT_PORT}")

    base_url = f"http://127.0.0.1:{AGENT_PORT}"

    try:
        # --------------------------------------------------------------
        # Step 1: Sign delegation JWT
        # --------------------------------------------------------------
        step(1, "Python orchestrator signs delegation JWT")

        delegation_jwt = sign_delegation(
            issuer_private_key=orch_priv,
            issuer_did=orch_did,
            subject_did=agent_did,
            scope=["read:db:customers"],
            ttl_seconds=3600,
        )
        claims = _decode_jwt_claims(delegation_jwt)
        jti = claims["jti"]
        exp_dt = datetime.fromtimestamp(float(claims["exp"]), tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        info("scope", str(["read:db:customers"]))
        info("jti", f"{jti[:8]}…")
        info("ttl", f"3600s → exp {exp_dt}")

        # Build TaskEnvelope (plain dict — wire format)
        def make_task(intent_type: str, params: dict | None = None) -> dict:
            return {
                "version": "1.0",
                "id": "demo-task-001",
                "intent": {"type": intent_type, "params": params or {}},
                "constraints": {
                    "budget_credits": 100,
                    "max_delegations": 5,
                    "allowed_capabilities": [],
                    "denied_capabilities": [],
                },
                "auth_chain": [delegation_jwt],
                "trace_id": "demo-trace-001",
                "state": "created",
            }

        # --------------------------------------------------------------
        # Step 2: queryCustomers — should succeed
        # --------------------------------------------------------------
        step(2, "Python → TS: queryCustomers (scope granted)")
        task = make_task("queryCustomers")
        arrow("out", f"POST /task  (intent: queryCustomers)")
        status, body = http_post(f"{base_url}/task", task)
        arrow("in", f"{status}  {json.dumps(body)}")
        if status == 200:
            ok("Auth chain verified, capability executed")
        else:
            fail(f"Unexpected status {status}")
            sys.exit(1)

        # --------------------------------------------------------------
        # Step 3: writeCustomer — should be rejected (ScopeError)
        # --------------------------------------------------------------
        step(3, "Python → TS: writeCustomer (scope NOT granted)")
        task3 = make_task("writeCustomer", {"name": "Evil Corp"})
        arrow("out", "POST /task  (intent: writeCustomer)")
        status3, body3 = http_post(f"{base_url}/task", task3)
        arrow("in", f"{status3}  {json.dumps(body3)}")
        if status3 == 403 and body3.get("error") == "scope_denied":
            ok("ScopeError: requires [write:db:customers], granted [read:db:customers]")
        else:
            fail(f"Expected 403 scope_denied, got {status3}: {body3}")
            sys.exit(1)

        # --------------------------------------------------------------
        # Step 4: Revoke JWT → soft-stop
        # --------------------------------------------------------------
        step(4, "Python revokes delegation mid-scenario")
        arrow("out", f"POST /revoke  {{jti: {jti[:8]}…}}")
        rev_status, rev_body = http_post(f"{base_url}/revoke", {"jti": jti})
        arrow("in", f"{rev_status}  {json.dumps(rev_body)}")

        # Now retry queryCustomers with the same (now-revoked) JWT
        task4 = make_task("queryCustomers")
        arrow("out", "POST /task  (intent: queryCustomers, jti revoked)")
        status4, body4 = http_post(f"{base_url}/task", task4)
        arrow("in", f"{status4}  {json.dumps(body4)}")
        if status4 == 403:
            ok("Agent correctly soft-stopped (jti revoked)")
        else:
            fail(f"Expected 403, got {status4}: {body4}")
            sys.exit(1)

        # --------------------------------------------------------------
        # Step 5: Render auth chain trace
        # --------------------------------------------------------------
        step(5, "Auth chain trace")
        known_keys = {orch_did: orch_pub}
        render_auth_chain([delegation_jwt], known_keys)

    finally:
        proc.terminate()
        proc.wait(timeout=5)
        if BOOTSTRAP_PATH.exists():
            BOOTSTRAP_PATH.unlink()

    print()
    rule()
    print("  Demo complete.")
    rule()
    print()


if __name__ == "__main__":
    main()

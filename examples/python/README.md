# Python example

One signed delegation. The worker may run `read_record`. `write_record` is rejected with `ScopeError` before its handler runs.

`worker.handle` enforces the chain (final subject, hop continuity, scope narrowing) and the capability scope. It does not consult a revocation registry. Call `verify_auth_chain` with `revocation_registry` when a revoked token must be rejected.

No API keys and no network calls.

## Run

From the repository root:

```bash
uv venv --python 3.12 /tmp/agentpassport-example-python
uv pip install --python /tmp/agentpassport-example-python/bin/python \
  -e packages/agentpassport \
  -r examples/python/requirements.txt
/tmp/agentpassport-example-python/bin/python examples/python/delegation.py
```

Outside this repo, install the published package instead of the editable path:

```bash
pip install agentpassport
python delegation.py
```

The script exits 0 only when `handle` accepts the chain, `read_record` returns the requested id, and `write_record` is denied without running its handler.

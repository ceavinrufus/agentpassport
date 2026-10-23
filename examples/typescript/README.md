# TypeScript example

The same flow as `examples/python`: one signed delegation, one allowed capability, one denied capability. `write_record` raises `ScopeError` before its handler runs.

No API keys and no network calls.

The dependency points at `packages/agentpassport-ts` in this repo, so the example is typechecked and run against the SDK you have checked out. This folder does not commit a lockfile: the local package hash changes whenever the SDK is rebuilt.

## Run

From the repository root:

```bash
cd packages/agentpassport-ts
npm ci
npm run build
cd ../../examples/typescript
npm install --no-package-lock
npm run typecheck
npm start
```

Outside this repo, point the dependency at the published package instead:

```bash
npm install @agentpassport/core tsx typescript @types/node
npx tsx delegation.ts
```

The script exits 0 only when the chain verifies, `read_record` returns the requested id, and `write_record` is denied without running its handler.

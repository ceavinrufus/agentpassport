# Examples

Runnable examples. Each one installs only what it needs, makes no network calls, and exits non-zero if the scope check does not behave as written.

| Example | What it shows |
| --- | --- |
| [langgraph](langgraph/README.md) | A delegation chain across a graph; `handle` checks the chain and the tool scope |
| [python](python/README.md) | One signed delegation and a scope check |
| [typescript](typescript/README.md) | The same flow in TypeScript |

CI smoke-runs all three on every pull request. See each directory's README for the install command.

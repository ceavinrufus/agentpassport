# Contributing to agentpassport

Thanks for your interest in contributing. Here's how to get started.

## Development Setup

```bash
git clone https://github.com/ceavinrufus/agentpassport
cd agentpassport
uv sync --all-packages
```

Run tests:

```bash
uv run pytest                                        # Python
cd packages/agentpassport-ts && npm ci && npm test  # TypeScript
```

Run linter:

```bash
uv run ruff check .
```

## Pull Requests

- Keep PRs focused — one concern per PR
- Add tests for new behavior
- Make sure CI passes before requesting review
- Write a clear description of what and why

## Reporting Bugs

Open a [GitHub issue](https://github.com/ceavinrufus/agentpassport/issues) with a minimal reproduction case.

## Security Issues

Do **not** open a public issue for security vulnerabilities. See [SECURITY.md](SECURITY.md).

## License

By contributing, you agree that your contributions will be licensed under the [Apache 2.0 License](LICENSE).

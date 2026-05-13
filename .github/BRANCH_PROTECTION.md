# Branch Protection Setup

GitHub branch protection rules must be configured manually in the repository settings.
This file documents the recommended settings for the `main` branch.

## Steps

1. Go to **Settings > Branches** in the GitHub repository.
2. Click **Add branch protection rule**.
3. Set **Branch name pattern** to `main`.

## Recommended Rules

| Setting | Value |
|---|---|
| Require a pull request before merging | Enabled |
| Required approving reviews | 1 |
| Dismiss stale pull request approvals when new commits are pushed | Enabled |
| Require status checks to pass before merging | Enabled |
| Required status checks | `test-python (3.11)`, `test-python (3.12)`, `test-typescript`, `lint-python`, `lint-typescript` |
| Require branches to be up to date before merging | Enabled |
| Require conversation resolution before merging | Enabled |
| Do not allow bypassing the above settings | Enabled |
| Restrict who can push to matching branches | Maintainers only |

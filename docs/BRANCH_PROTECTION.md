# Branch Protection Rules

Recommended GitHub branch protection settings for the `main` branch to enforce code quality and safe merges.

## Setup

Go to **Settings → Branches → Add branch protection rule** and set **Branch name pattern** to `main`.

## Required Settings

### 1. Require a pull request before merging

- **Required approving reviews:** 1
- **Dismiss stale pull request approvals when new commits are pushed:** ✅
- **Require review from Code Owners:** optional (enable if you add a `CODEOWNERS` file)

### 2. Require status checks to pass before merging

Enable **Require branches to be up to date before merging** and add these required checks:

| Status Check | Source | Purpose |
|--------------|--------|---------|
| `lint` | `ci.yml` | Flake8 passes |
| `test (3.12)` | `ci.yml` | Tests pass on latest Python |
| `docker` | `ci.yml` | Docker build + smoke test |

> **Tip:** The check names correspond to the `jobs:` keys in `.github/workflows/ci.yml`. You may also add `test (3.10)` and `test (3.11)` if you want all matrix legs required.

### 3. Require linear history

- ✅ **Require linear history**

Forces squash-merge or rebase-merge, keeping `main` clean and bisectable.

### 4. Restrict push access

- ✅ **Restrict who can push to matching branches**
- Add only maintainer accounts / deploy bots
- ✅ **Do not allow force pushes**
- ✅ **Do not allow deletions**

### 5. Require conversation resolution

- ✅ **Require conversation resolution before merging**

Ensures all PR review comments are addressed.

## Dependabot Auto-Merge Compatibility

The `auto-merge.yml` workflow automatically approves and merges minor/patch Dependabot PRs. For this to work with branch protection:

1. The `GITHUB_TOKEN` used by the workflow has permission to approve PRs
2. Status checks must pass before the auto-merge completes
3. Major version bumps are **not** auto-merged — they get a `needs-manual-review` label

If you require CODEOWNERS review, add Dependabot to the bypass list:

```
Settings → Branches → main → Allow specified actors to bypass required pull requests
→ Add: dependabot[bot]
```

## Recommended Optional Settings

| Setting | Value | Reason |
|---------|-------|--------|
| Include administrators | ✅ | Enforce rules for everyone |
| Allow auto-merge | ✅ | Let Dependabot workflow merge |
| Require signed commits | Optional | Adds provenance but more friction |

## Quick Checklist

```
[ ] Branch protection rule exists for `main`
[ ] PR reviews required (min 1)
[ ] Stale review dismissal enabled
[ ] Required status checks: lint, test (3.12), docker
[ ] Linear history required
[ ] Force push disabled
[ ] Branch deletion disabled
[ ] Conversation resolution required
[ ] Dependabot bypass configured (if using CODEOWNERS)
```

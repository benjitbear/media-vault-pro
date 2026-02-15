# Governance

## Project Maintainers

| Role | Name | Responsibilities |
|------|------|-----------------|
| Lead Maintainer | Benjamin Poppe | Final decision authority, release management, security |

## Decision-Making Process

1. **Minor changes** (bug fixes, small features, doc updates) — maintainer reviews and merges directly
2. **Significant changes** (new features, breaking changes, architecture) — discussed in a GitHub issue before implementation
3. **Breaking changes** — require a changelog entry, version bump, and migration path

## Contribution Review

- All contributions go through pull requests
- The lead maintainer reviews and approves PRs
- CI checks (tests, linting) must pass before merge
- Breaking changes require updating `CHANGELOG.md`

## Release Process

1. Update version in `pyproject.toml` and `src/__init__.py`
2. Update `CHANGELOG.md` with all changes
3. Create a git tag: `git tag v0.x.0`
4. Push tag to trigger release workflow
5. Update Docker image if applicable

## Communication

- **Issues:** Bug reports and feature requests via GitHub Issues
- **Pull Requests:** Code contributions and discussions
- **Security:** Email `ben@medialibrary.local` (see [SECURITY.md](SECURITY.md))

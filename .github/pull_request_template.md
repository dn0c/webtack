## Description

<!-- Provide a concise description of what this PR does and why it is needed. -->

## Related Issues

<!-- Reference related issues (e.g. Fixes #123, Closes #456) -->

## Type of Change

- [ ] 🐛 Bug fix (non-breaking change which fixes an issue)
- [ ] ✨ New feature (non-breaking change adding functionality)
- [ ] 📝 Documentation update (README, SPECIFICATION, guides)
- [ ] 🧪 Tests / CI enhancement
- [ ] 📦 Exporter / format enhancement
- [ ] ⚡ Performance optimization / refactor

## Architectural Alignment Checklist

- [ ] Respects the **Content Sidecar Pattern** (assets and metadata colocated in per-atom directories).
- [ ] Respects **Filesystem as Canonical Truth** (SQLite is disposable and rebuilt cleanly via `reindex`).
- [ ] Preserves backward compatibility (does not break existing `atom.json` files on disk).
- [ ] Does not introduce heavy unnecessary third-party dependencies.

## Verification & Testing

- [ ] Specimen vault validates cleanly:
  ```bash
  python3 curate.py --vault fixtures/demo_vault validate
  ```
- [ ] All automated unit & integration tests pass:
  ```bash
  python3 -m unittest discover -s tests -v
  ```
- [ ] Added new test cases covering the new behavior (if applicable).

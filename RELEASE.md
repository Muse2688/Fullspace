# Releasing Fullspace to PyPI

Releases are fully automated: pushing a version tag triggers
[`.github/workflows/release.yml`](.github/workflows/release.yml), which runs
tests → builds sdist + wheel → publishes to PyPI via **Trusted Publishing
(OIDC)** — no API token is stored anywhere.

```
git tag v0.2.0 && git push origin v0.2.0
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│ test   pytest + mypy + tag↔version consistency check    │
│   └▶ build   python -m build  (sdist + wheel)           │
│         └▶ publish   PyPI via Trusted Publishing        │
│                (environment: pypi, OIDC)                │
└─────────────────────────────────────────────────────────┘
```

## 0. Prerequisites (one-time)

1. **PyPI Trusted Publisher** — open
   <https://pypi.org/manage/project/fullspace/publishing/> → *Add a pending
   publisher* → GitHub, and fill in:
   - Owner: `Muse2688` · Repository: `Fullspace`
   - Workflow name: `release.yml`
   - Environment: **`pypi`** ← must match the workflow's `environment:` exactly,
     or the OIDC claim check fails.
2. **GitHub environment** — repo *Settings → Environments* → create `pypi`
   (optional but recommended: add required reviewers there to gate publishes).
3. The workflow file must exist on the **default branch** (it does).

## 1. Every release (three steps)

```bash
# ① Bump the version — the single source of truth is fullspace/__init__.py:
#      __version__ = "0.2.0"
#    (pyproject.toml reads it dynamically; do NOT edit a version there.)

# ② Commit and push to master
git add -A && git commit -m "-release 0.2.0" && git push origin master

# ③ Push the tag — this is the publish button
git tag v0.2.0 && git push origin v0.2.0
```

The pipeline refuses to publish if the tag does not match the package version
(the `Verify tag matches pyproject version` step), so a mistagged push fails
fast instead of shipping a wrong version to PyPI (uploads are irreversible —
a version number can never be re-uploaded).

Version-numbering guide: bug fixes `0.1.0 → 0.1.1`; new backwards-compatible
features `0.1.0 → 0.2.0`; breaking API changes bump the major.

## 2. Optional dry-run on TestPyPI

Before a first release (or after touching the pipeline), rehearse by pointing
`gh-action-pypi-publish` at TestPyPI: temporarily add
`with: { repository-url: https://test.pypi.org/legacy/ }` to the publish step,
push a throwaway tag (e.g. `v0.0.0-rc1`), verify
`pip install -i https://test.pypi.org/simple/ fullspace`, then revert.

## 3. Manual fallback (no CI)

```bash
pip install -U build twine
python -m build && python -m twine check dist/*
python -m twine upload dist/*     # username: __token__, password: pypi-…
```

## 4. After publishing

- Create the **GitHub Release** from the tag (the PyPI link auto-appears —
  the project URL is set in `pyproject.toml`).
- Watch the Actions run: <https://github.com/Muse2688/Fullspace/actions/workflows/release.yml>
- The version on PyPI: <https://pypi.org/project/fullspace/>

## Notes

- `python -m pip install fullspace` stays lightweight: only `numpy` is a hard
  runtime dependency; FAISS/USearch/Milvus/Neo4j/sentence-transformers/LangGraph/
  PyMySQL are all optional extras.
- `dist/`, `build/`, `*.egg-info` are gitignored — build artifacts are never
  committed; CI builds them fresh from the tag.
- Version history is one place: `git tag -l` mirrors what is on PyPI.

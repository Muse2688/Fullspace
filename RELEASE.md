# Releasing Fullspace to PyPI

Fullspace is publish-ready: it builds to a clean wheel + sdist (`twine check`
passes) and the wheel installs and runs in a fresh venv. This is the release
runbook.

## 0. Prerequisites (one-time)

- A **PyPI** account: <https://pypi.org/account/register/>
- An **API token**: Account settings → API tokens → Add token
  (scope: *Entire account*, or scoped to the `fullspace` project after first
  upload). Copy it — it starts with `pypi-`.
- Build tools: `pip install -U build twine`

> PyPI names are **permanent**: once `fullspace` is published, the name can't be
> reused even after deletion. `0.1.0` as a first publish is fine.

## 1. Pre-flight (automated checks)

```bash
python -m pytest tests/ -q        # all tests green
python -m mypy fullspace          # 0 errors
rm -rf dist build fullspace.egg-info
python -m build                   # -> dist/fullspace-<ver>-py3-none-any.whl + .tar.gz
python -m twine check dist/*      # metadata + README render OK (must pass)
```

## 2. (Optional) Dry-run on TestPyPI

```bash
python -m twine upload --repository testpypi dist/*
# then verify it installs:
pip install -i https://test.pypi.org/simple/ fullspace
```

## 3. Publish to PyPI

Two paths — automated (recommended) or manual.

### 3a. Automated via GitHub Actions (Trusted Publishing, no token stored)

`release.yml` already builds, checks, and publishes on a version-tag push. One-time
PyPI setup:

1. Open <https://pypi.org/manage/project/fullspace/publishing/> → **Add a publisher** → GitHub.
2. Fill: Owner `Muse2688`, Repository `Fullspace`, Workflow `release.yml`,
   Environment *(leave blank)*. Add.
3. Commit `release.yml` to the **default branch** and push it (the workflow file must
   exist on the default branch for tag pushes to trigger it).

Then every release is one tag:

```bash
# bump version in pyproject.toml first, then commit
git tag v0.1.1
git push origin v0.1.1          # CI: test -> build -> publish to PyPI
```

### 3b. Manual (first publish / fallback)

```bash
python -m twine upload dist/*
# username: __token__
# password: <paste the pypi- token>
```

## 4. After publishing

- Tag the release: `git tag v0.1.0 && git push --tags`.
- Fill in the GitHub Release (the PyPI link auto-appears once the project URL is
  set in `pyproject.toml`, which it is).
- Bump `version` in `pyproject.toml` for the next dev cycle.

## Notes

- Only `numpy` is a hard runtime dependency; everything else (FAISS,
  sentence-transformers, UMAP, LangGraph) is an optional extra — so
  `pip install fullspace` stays lightweight.
- The wheel contains only the importable package + metadata; the sdist (via
  `MANIFEST.in`) also bundles the bilingual READMEs, CONTRIBUTING, docs, and CI.
- `dist/`, `build/`, and `*.egg-info` are gitignored — build artifacts are never
  committed.

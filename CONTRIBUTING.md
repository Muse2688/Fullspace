# Contributing to Fullspace

Thanks for your interest in improving Fullspace! This is a short guide to get your
contribution landed.

## Development setup

```bash
git clone https://github.com/Muse2688/Fullspace.git
cd Fullspace
pip install -e ".[langgraph,dev]"   # core + LangGraph interop/eval + pytest + mypy
pip install faiss-cpu               # for the FAISS ANN tests
```

## Before you open a pull request

The project keeps two gates green — please run both:

```bash
python -m pytest tests/ -q      # all tests must pass
python -m mypy fullspace        # must be clean (0 errors)
```

If you add a feature or fix a bug, add a test under `tests/` that covers it. If you add
a new optional dependency, guard its import and keep the core runnable without it
(Fullspace's zero-heavy-dependency default is a feature, not an accident).

## Conventions

- **Honest benchmarks.** Any claim that Fullspace beats (or ties) another framework must
  be backed by a case in `fullspace/eval/` that can be re-run. Rigged benchmarks undermine
  credibility — don't.
- **Projection is for humans only.** Routing must never use the 3D projection; it always
  operates in the high-dimensional manifold.
- **Backward compatibility.** The discrete flow is the LangGraph-equivalent baseline;
  don't break it. Existing tests are the contract.
- Match the surrounding code's style, density, and docstring conventions.

## Pull request flow

1. Open an issue first for non-trivial changes, so we can align on direction.
2. Keep PRs focused; one logical change per PR.
3. Ensure both gates above pass and describe *what* changed and *why*.

## License

By contributing, you agree your contributions are licensed under the project's
[MIT license](LICENSE).

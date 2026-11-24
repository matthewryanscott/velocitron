# Bundled celpy

This directory is the canonical bundled celpy. Its imports point at `velocitron_cel`. Edit it here. The umbrella does not vendor a second copy.

This is the `celpy` package of [cel-python](https://github.com/cloud-custodian/cel-python) 0.5.0, by Capital One Services, LLC, under the Apache License 2.0 (`LICENSE` in this directory). velocitron bundles it so that installing velocitron does not need `google-re2` where that package has no wheel (ADR 0054).

Source: the PyPI sdist `cel_python-0.5.0.tar.gz` (sha256 `3eb0a619e8df0f338d0430cda01427a742e77e3c433a1c7c3ebd409cd804c45a`), directory `src/celpy`. Its files equal those of the PyPI wheel `cel_python-0.5.0-py3-none-any.whl`.

Taken: `__init__.py`, `adapter.py`, `celparser.py`, `celtypes.py`, `evaluation.py`, `cel.lark`. Left out: `__main__.py` (the `celpy` command line) and `c7nlib.py` (Cloud Custodian functions), which velocitron does not use and which need `jmespath` and `pyyaml`.

Changes, each marked at the top of the changed file:

- `__init__.py`, `adapter.py`, `evaluation.py`: imports of `celpy` point at `velocitron_cel._vendor.celpy`.
- `evaluation.py`: when `import re2` fails, `re2` is `velocitron_cel._re2_standin`, which is backed by Python's `re`.
- `celtypes.py`: ordering and equality compare `int`, `uint`, and `double` across those types, as the CEL spec requires. Past 2^53 the comparison converts the integer to double, matching the CEL conformance `*_lossy_double` cases. Map lookup finds a key by that same equality, so a double index can select an int or uint key. Arithmetic still does not mix numeric types.

To update: replace these files with the new release's, apply the same changes, and update the version here and the dependencies in `packages/cel/python/pyproject.toml` (cel-python's own, less `jmespath` and `pyyaml`) and ADR 0054. The umbrella depends on this package; it does not carry the tree.

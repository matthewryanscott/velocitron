# Python integration tests

`implementations/python` is the cross-package pytest project. It is not an
installable library. `tool.uv.package` is false, and the project name is
`velocitron-python-tests`.

Sync it and run the suite:

```console
cd implementations/python
uv sync
uv run pytest
```

Optional CEL backends are extras on this project and forward to
`velocitron-cel`. Auto-detection uses Rust when that extra is installed,
and otherwise bundled celpy. `cel-cpp` stays installable as a conformance
reference and is selected by passing `CelExprAdapter()` (ADR 0066).

```console
uv sync --extra cel-rust
uv sync --extra cel-cpp
```

The `velocitron` and `velocitron-viz` console scripts come from the
`velocitron-cli` dependency. Library imports use the `velocitron_*`
packages under `packages/`. `velocitron_runtime.Engine` is the synchronous
engine with the default CEL adapter filled in.

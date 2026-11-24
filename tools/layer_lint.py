#!/usr/bin/env python3
"""Fail on import cycles and layer-allow violations in both languages.

``layers.yaml`` is the only allow-list. This script reads it with the
standard library (no PyYAML, import-linter, or dependency-cruiser) so the
Python and TypeScript checks cannot drift into two configs. See
``docs/layers.md``.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAYERS_PATH = ROOT / "layers.yaml"

_ASSET_SUFFIXES = (".json", ".md", ".txt", ".lark", ".css", ".svg", ".png", ".yaml", ".yml")
_SKIP_DIRS = {
    ".venv",
    "node_modules",
    "dist",
    "__pycache__",
    ".pytest_cache",
    "conformance",
}


@dataclass(frozen=True)
class Layer:
    name: str
    python: str | None
    typescript: str | None
    allow: frozenset[str]


@dataclass(frozen=True)
class Import:
    lineno: int
    target: str
    type_only: bool
    module_level: bool
    relative: bool


def parse_layers(text: str) -> dict[str, Layer]:
    """Parse the ``layers:`` mapping this repository writes."""
    layers: dict[str, Layer] = {}
    current: str | None = None
    fields: dict[str, object] = {}

    def finish() -> None:
        if current is None:
            return
        allow = fields.get("allow", ())
        if not isinstance(allow, tuple):
            raise ValueError(f"{current}: allow must be a list")
        python = fields.get("python")
        typescript = fields.get("typescript")
        layers[current] = Layer(
            name=current,
            python=python if isinstance(python, str) else None,
            typescript=typescript if isinstance(typescript, str) else None,
            allow=frozenset(str(item) for item in allow),
        )

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line.strip() == "layers:":
            continue
        if not line.startswith(" "):
            raise ValueError(f"unexpected line in layers.yaml: {raw}")
        indent = len(line) - len(line.lstrip(" "))
        body = line.strip()
        if indent == 2 and body.endswith(":"):
            finish()
            current = body[:-1]
            fields = {}
            continue
        if current is None or indent != 4 or ":" not in body:
            raise ValueError(f"unexpected line in layers.yaml: {raw}")
        key, value = (part.strip() for part in body.split(":", 1))
        if key == "allow":
            if value == "[]":
                fields["allow"] = ()
            else:
                inner = value.strip()
                if not (inner.startswith("[") and inner.endswith("]")):
                    raise ValueError(f"{current}.allow is not a one-line list")
                names = [item.strip() for item in inner[1:-1].split(",") if item.strip()]
                fields["allow"] = tuple(names)
        else:
            fields[key] = value.strip().strip('"').strip("'")
    finish()
    unknown = sorted(
        f"{layer.name} allows unknown layer {name}"
        for layer in layers.values()
        for name in layer.allow
        if name not in layers
    )
    if unknown:
        raise ValueError("; ".join(unknown))
    return layers


def python_imports(source: str, module: str, is_package: bool) -> list[Import]:
    tree = ast.parse(source)
    found: list[Import] = []

    class Collector(ast.NodeVisitor):
        def __init__(self) -> None:
            self.type_checking = 0
            self.scope = 0

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._enter(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._enter(node)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self._enter(node)

        def visit_Lambda(self, node: ast.Lambda) -> None:
            self.scope += 1
            self.generic_visit(node)
            self.scope -= 1

        def _enter(self, node: ast.AST) -> None:
            self.scope += 1
            self.generic_visit(node)
            self.scope -= 1

        def visit_If(self, node: ast.If) -> None:
            if self.scope == 0 and _is_type_checking(node.test):
                self.type_checking += 1
                for stmt in node.body:
                    self.visit(stmt)
                self.type_checking -= 1
                for stmt in node.orelse:
                    self.visit(stmt)
                return
            self.generic_visit(node)

        def visit_Import(self, node: ast.Import) -> None:
            for alias in node.names:
                found.append(_edge(node.lineno, alias.name, False, self))

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            if node.level:
                target = _resolve_relative(module, is_package, node.level, node.module)
                if node.module is None:
                    base = target
                    for alias in node.names:
                        name = f"{base}.{alias.name}" if base else alias.name
                        found.append(_edge(node.lineno, name, True, self))
                    return
                found.append(_edge(node.lineno, target, True, self))
                return
            if node.module:
                found.append(_edge(node.lineno, node.module, False, self))

    Collector().visit(tree)
    return found


def _edge(lineno: int, target: str, relative: bool, collector: ast.NodeVisitor) -> Import:
    return Import(
        lineno=lineno,
        target=target,
        type_only=collector.type_checking > 0,  # type: ignore[attr-defined]
        module_level=collector.scope == 0,  # type: ignore[attr-defined]
        relative=relative,
    )


def _is_type_checking(expr: ast.expr) -> bool:
    if isinstance(expr, ast.Name):
        return expr.id == "TYPE_CHECKING"
    if isinstance(expr, ast.Attribute):
        return expr.attr == "TYPE_CHECKING"
    return False


def _resolve_relative(module: str, is_package: bool, level: int, target: str | None) -> str:
    package = module if is_package else module.rsplit(".", 1)[0]
    parts = package.split(".") if package else []
    if level > 1:
        parts = parts[: -(level - 1)]
    if target:
        parts.extend(target.split("."))
    return ".".join(parts)


def typescript_imports(source: str) -> list[Import]:
    stripped = _strip_ts_comments(source)
    lines = stripped.splitlines()
    found: list[Import] = []
    index = 0
    while index < len(lines):
        stripped_line = lines[index].strip()
        if not _starts_import(stripped_line):
            dynamic = re.search(r"""import\s*\(\s*['"]([^'"]+)['"]\s*\)""", lines[index])
            if dynamic:
                found.append(
                    Import(
                        lineno=index + 1,
                        target=dynamic.group(1),
                        type_only=False,
                        module_level=False,
                        relative=dynamic.group(1).startswith("."),
                    )
                )
            index += 1
            continue
        buf = [lines[index]]
        depth = lines[index].count("{") + lines[index].count("(") - lines[index].count("}") - lines[index].count(")")
        while True:
            statement = "\n".join(buf)
            if depth <= 0 and _import_finished(statement):
                break
            index += 1
            if index >= len(lines):
                break
            buf.append(lines[index])
            depth += lines[index].count("{") + lines[index].count("(")
            depth -= lines[index].count("}") + lines[index].count(")")
        statement = "\n".join(buf)
        spec = _specifier(statement)
        if spec is not None:
            found.append(
                Import(
                    lineno=index - len(buf) + 2,
                    target=spec,
                    type_only=_type_only(statement),
                    module_level=True,
                    relative=spec.startswith("."),
                )
            )
        index += 1
    return found


def _starts_import(line: str) -> bool:
    if line.startswith("import "):
        return True
    return re.match(r"export\s+(type\s+)?(\*|\{)", line) is not None


def _import_finished(statement: str) -> bool:
    if re.search(r"""\bfrom\s+['"][^'"]+['"]""", statement):
        return True
    compact = " ".join(statement.split())
    return re.match(r"""import\s+['"][^'"]+['"]""", compact) is not None


def _specifier(statement: str) -> str | None:
    match = re.search(r"""\bfrom\s+['"]([^'"]+)['"]""", statement)
    if match:
        return match.group(1)
    compact = " ".join(statement.split())
    side = re.match(r"""import\s+['"]([^'"]+)['"]""", compact)
    if side:
        return side.group(1)
    return None


def _type_only(statement: str) -> bool:
    compact = " ".join(statement.split())
    if compact.startswith("import type ") or compact.startswith("export type "):
        return True
    match = re.search(r"\{([^}]*)\}", statement, re.DOTALL)
    if match is None:
        return False
    parts = [part.strip() for part in match.group(1).split(",") if part.strip()]
    if not parts or not all(part.startswith("type ") for part in parts):
        return False
    head = compact.split("{", 1)[0]
    return re.match(r"(import|export)\s+\w", head) is None and "import *" not in head and "export *" not in head


def _strip_ts_comments(source: str) -> str:
    out: list[str] = []
    index = 0
    limit = len(source)
    state = "code"
    while index < limit:
        char = source[index]
        nxt = source[index + 1] if index + 1 < limit else ""
        if state == "code":
            if char == "/" and nxt == "/":
                state = "line"
                out.append(" ")
                index += 2
                continue
            if char == "/" and nxt == "*":
                state = "block"
                out.append(" ")
                index += 2
                continue
            if char in {"'", '"', "`"}:
                state = char
                out.append(char)
                index += 1
                continue
            out.append(char)
            index += 1
            continue
        if state == "line":
            if char == "\n":
                state = "code"
                out.append("\n")
            else:
                out.append(" ")
            index += 1
            continue
        if state == "block":
            if char == "*" and nxt == "/":
                state = "code"
                out.append("  ")
                index += 2
                continue
            out.append("\n" if char == "\n" else " ")
            index += 1
            continue
        out.append(char)
        if char == "\\" and index + 1 < limit:
            out.append(source[index + 1])
            index += 2
            continue
        if char == state:
            state = "code"
        index += 1
    return "".join(out)


def find_cycles(graph: Mapping[str, Iterable[str]]) -> list[tuple[str, ...]]:
    """Return each runtime cycle once, rotated so the smallest node is first."""
    color: dict[str, int] = {}
    found: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()

    def walk(node: str, stack: list[str]) -> None:
        color[node] = 1
        stack.append(node)
        for nxt in sorted(set(graph.get(node, ()))):
            if nxt == node:
                continue
            state = color.get(nxt, 0)
            if state == 1:
                start = stack.index(nxt)
                body = stack[start:]
                pivot = min(range(len(body)), key=lambda item: body[item])
                rotated = tuple(body[pivot:] + body[:pivot])
                if rotated not in seen:
                    seen.add(rotated)
                    found.append(rotated)
            elif state == 0:
                walk(nxt, stack)
        stack.pop()
        color[node] = 2

    for node in sorted(graph):
        if color.get(node, 0) == 0:
            walk(node, [])
    return found


def lint(layers: dict[str, Layer] | None = None) -> list[str]:
    catalog = layers if layers is not None else parse_layers(LAYERS_PATH.read_text(encoding="utf-8"))
    problems: list[str] = []
    problems.extend(_declared_dependency_problems(catalog))
    py_graph: dict[str, set[str]] = {}
    ts_graph: dict[str, set[str]] = {}
    problems.extend(_python_import_problems(catalog, py_graph))
    problems.extend(_typescript_import_problems(catalog, ts_graph))
    for cycle in find_cycles(py_graph):
        problems.append("runtime import cycle: " + " -> ".join((*cycle, cycle[0])))
    for cycle in find_cycles(ts_graph):
        problems.append("runtime import cycle: " + " -> ".join((*cycle, cycle[0])))
    return problems


def _python_roots(layer: Layer) -> list[tuple[Path, Path]]:
    """Return ``(module root, scan root)`` pairs. The module root is the parent of the top package."""
    if layer.name == "spec":
        base = ROOT / "packages" / "spec"
    elif layer.python:
        base = ROOT / "packages" / layer.name / "python"
    else:
        return []
    pairs = [(base / "src", base / "src")]
    if (base / "tests").is_dir():
        pairs.append((base, base / "tests"))
    elif layer.name == "spec" and (base / "src").is_dir():
        pairs = [(base / "src", base / "src")]
    return [(module_root, scan) for module_root, scan in pairs if scan.is_dir()]


def _typescript_roots(layer: Layer) -> list[Path]:
    if layer.name == "spec":
        return [ROOT / "packages" / "spec"]
    if layer.typescript:
        base = ROOT / "packages" / layer.name / "typescript"
        return [path for path in (base / "src", base / "test") if path.is_dir()]
    return []


def _python_import_problems(layers: dict[str, Layer], graph: dict[str, set[str]]) -> list[str]:
    by_python = {layer.python: layer for layer in layers.values() if layer.python}
    problems: list[str] = []
    for layer in layers.values():
        for module_root, scan in _python_roots(layer):
            for path in _python_files(scan):
                module, is_package = _python_module(path, module_root)
                try:
                    imports = python_imports(path.read_text(encoding="utf-8"), module, is_package)
                except SyntaxError as exc:
                    problems.append(f"{_rel(path)}:{exc.lineno}: syntax error: {exc.msg}")
                    continue
                vendor = "_vendor" in path.parts
                for item in imports:
                    owner = _python_layer(item.target, by_python)
                    if owner is None or owner.name == layer.name:
                        if (
                            item.module_level
                            and not item.type_only
                            and not vendor
                            and not _generated_pair(path, item.target)
                        ):
                            graph.setdefault(module, set()).add(item.target)
                        continue
                    problems.extend(
                        _edge_problems(
                            layer,
                            owner,
                            item.target,
                            public=item.target == owner.python,
                            where=f"{_rel(path)}:{item.lineno}",
                        )
                    )
                    if item.module_level and not item.type_only and owner.python:
                        graph.setdefault(module, set()).add(owner.python)
    return problems


def _typescript_import_problems(layers: dict[str, Layer], graph: dict[str, set[str]]) -> list[str]:
    by_name = {layer.typescript: layer for layer in layers.values() if layer.typescript}
    problems: list[str] = []
    for layer in layers.values():
        entry = _ts_entry(layer)
        for scan in _typescript_roots(layer):
            for path in _ts_files(scan):
                node = _ts_node(path)
                try:
                    imports = typescript_imports(path.read_text(encoding="utf-8"))
                except UnicodeError as exc:
                    problems.append(f"{_rel(path)}: cannot read: {exc}")
                    continue
                for item in imports:
                    if item.relative:
                        if item.target.endswith(_ASSET_SUFFIXES):
                            continue
                        resolved = _resolve_ts(path, item.target)
                        if resolved is None:
                            problems.append(
                                f"{_rel(path)}:{item.lineno}: unresolved relative import {item.target}"
                            )
                            continue
                        owner = _layer_containing(resolved, layers)
                        target_node = _ts_node(resolved)
                        if owner is None or owner.name == layer.name:
                            if (
                                item.module_level
                                and not item.type_only
                                and not _generated_pair(path, target_node)
                            ):
                                graph.setdefault(node, set()).add(target_node)
                            continue
                        problems.append(
                            f"{_rel(path)}:{item.lineno}: {layer.name} imports {owner.name} "
                            "through a relative path instead of that package's public root"
                        )
                        if item.module_level and not item.type_only and entry and owner.typescript:
                            other_entry = _ts_entry(owner)
                            if other_entry:
                                graph.setdefault(node, set()).add(_ts_node(other_entry))
                        continue
                    owner = _ts_layer(item.target, by_name)
                    if owner is None:
                        continue
                    if owner.name == layer.name:
                        continue
                    problems.extend(
                        _edge_problems(
                            layer,
                            owner,
                            item.target,
                            public=item.target == owner.typescript,
                            where=f"{_rel(path)}:{item.lineno}",
                        )
                    )
                    if item.module_level and not item.type_only:
                        other_entry = _ts_entry(owner)
                        if other_entry:
                            graph.setdefault(node, set()).add(_ts_node(other_entry))
    return problems


def _edge_problems(source: Layer, owner: Layer, target: str, *, public: bool, where: str) -> list[str]:
    problems: list[str] = []
    if owner.name not in source.allow:
        problems.append(
            f"{where}: {source.name} imports {owner.name} via {target}, which its allow list does not permit"
        )
    if not public:
        problems.append(
            f"{where}: {source.name} imports {target} below the public package root of {owner.name}"
        )
    return problems


def _declared_dependency_problems(layers: dict[str, Layer]) -> list[str]:
    by_dist = {layer.python.replace("_", "-"): layer for layer in layers.values() if layer.python}
    by_npm = {layer.typescript: layer for layer in layers.values() if layer.typescript}
    problems: list[str] = []
    for layer in layers.values():
        for path in _pyprojects(layer):
            text = path.read_text(encoding="utf-8")
            for lineno, name in _project_dependencies(text):
                owner = by_dist.get(name)
                if owner is None or owner.name == layer.name:
                    continue
                problems.extend(
                    _edge_problems(layer, owner, name, public=True, where=f"{_rel(path)}:{lineno}")
                )
        for path in _package_jsons(layer):
            data = json.loads(path.read_text(encoding="utf-8"))
            for field in ("dependencies", "peerDependencies"):
                for name in data.get(field, {}):
                    owner = by_npm.get(name)
                    if owner is None or owner.name == layer.name:
                        continue
                    problems.extend(
                        _edge_problems(layer, owner, name, public=True, where=f"{_rel(path)}:1")
                    )
    return problems


def _pyprojects(layer: Layer) -> list[Path]:
    if layer.name == "spec":
        path = ROOT / "packages" / "spec" / "pyproject.toml"
        return [path] if path.is_file() else []
    path = ROOT / "packages" / layer.name / "python" / "pyproject.toml"
    return [path] if path.is_file() else []


def _package_jsons(layer: Layer) -> list[Path]:
    if layer.name == "spec":
        path = ROOT / "packages" / "spec" / "package.json"
        return [path] if path.is_file() else []
    path = ROOT / "packages" / layer.name / "typescript" / "package.json"
    return [path] if path.is_file() else []


def _project_dependencies(text: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    in_project = False
    in_deps = False
    depth = 0
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if line.startswith("[") and line.endswith("]"):
            in_project = line == "[project]"
            in_deps = False
            continue
        if not in_project:
            continue
        if not in_deps and line.startswith("dependencies"):
            if "[" not in line:
                continue
            in_deps = True
            depth = 0
        if not in_deps:
            continue
        depth += line.count("[") - line.count("]")
        for match in re.finditer(r"""['"]([A-Za-z0-9_.-]+)""", line):
            found.append((lineno, match.group(1)))
        if depth <= 0:
            in_deps = False
    return found


def _generated_pair(path: Path, target: str) -> bool:
    """ANTLR emits a parser/visitor import cycle. Skip edges that stay inside ``generated``."""
    if "generated" not in path.parts:
        return False
    return ".generated" in target or "/generated/" in target


def _python_layer(module: str, by_python: dict[str, Layer]) -> Layer | None:
    best: Layer | None = None
    best_len = -1
    for name, layer in by_python.items():
        if module == name or module.startswith(name + "."):
            if len(name) > best_len:
                best = layer
                best_len = len(name)
    return best


def _ts_layer(specifier: str, by_name: dict[str, Layer]) -> Layer | None:
    best: Layer | None = None
    best_len = -1
    for name, layer in by_name.items():
        if specifier == name or specifier.startswith(name + "/"):
            if len(name) > best_len:
                best = layer
                best_len = len(name)
    return best


def _layer_containing(path: Path, layers: dict[str, Layer]) -> Layer | None:
    for layer in layers.values():
        for scan in _typescript_roots(layer):
            if path.is_relative_to(scan):
                return layer
    return None


def _ts_entry(layer: Layer) -> Path | None:
    for scan in _typescript_roots(layer):
        for candidate in (scan / "index.ts", scan / "index.d.ts"):
            if candidate.is_file():
                return candidate
    return None


def _resolve_ts(source: Path, specifier: str) -> Path | None:
    base = specifier
    if base.endswith(".js"):
        base = base[:-3]
    elif base.endswith(".mjs"):
        base = base[:-4]
    start = (source.parent / base).resolve()
    candidates = [
        start.with_suffix(".ts"),
        start.with_suffix(".tsx"),
        start.with_suffix(".mts"),
        start.with_suffix(".d.ts"),
        start / "index.ts",
        start / "index.d.ts",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _python_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*.py")):
        if _SKIP_DIRS.intersection(path.parts):
            continue
        yield path


def _ts_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in {".ts", ".tsx", ".mts"} and not path.name.endswith(".d.ts"):
            continue
        if path.suffix not in {".ts", ".tsx", ".mts"} and not path.name.endswith(".d.ts"):
            continue
        if _SKIP_DIRS.intersection(path.parts):
            continue
        if path.name.endswith(".d.ts") or path.suffix in {".ts", ".tsx", ".mts"}:
            yield path


def _python_module(path: Path, module_root: Path) -> tuple[str, bool]:
    relative = path.relative_to(module_root).with_suffix("")
    parts = list(relative.parts)
    is_package = parts[-1] == "__init__"
    if is_package:
        parts = parts[:-1]
    return ".".join(parts), is_package


def _ts_node(path: Path) -> str:
    relative = path.relative_to(ROOT).as_posix()
    if relative.endswith(".d.ts"):
        return relative[: -len(".d.ts")]
    return str(Path(relative).with_suffix(""))


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def main() -> int:
    try:
        problems = lint()
    except ValueError as exc:
        print(f"layers.yaml: {exc}", file=sys.stderr)
        return 1
    if problems:
        for problem in problems:
            print(problem)
        print(f"{len(problems)} layer lint problem(s)", file=sys.stderr)
        return 1
    print("Layer imports match layers.yaml.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

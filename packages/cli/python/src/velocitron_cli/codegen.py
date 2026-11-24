"""`velocitron codegen`: generate one net module from a `.petrinet` leaf,
or one composition module (plus every nested member's) from a composition.

The CLI owns nothing the generator does not: it reads the file, runs both
pipelines side by side, prints one error per line on a generation failure,
and either writes the module(s) (`--out`, default `<stem>_net.py` beside
`FILE`) or compares them (`--check`: byte-diff, exit 1, write nothing).

A leaf writes its one module. A composition writes every module the
generator produced — the composition's beside the composition file, each
member's beside the member file — so `--check` on a composition catches a
stale member too (any difference, exit 1, nothing written).
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path, PurePath

from velocitron_codegen import CodegenError, GeneratedModule, generate_module
from velocitron_dsl import PetrinetDslError, lower_petrinet_text
from velocitron_petrinet import (
    NetValidationError,
    compile_petrinet_text,
    parse_net,
    read_petrinet_text,
)


def _base_name(path: str) -> str:
    return PurePath(path).name


def _output_path(path: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    stem = _base_name(path).removesuffix(".petrinet")
    return stem + "_net.py"


def generate(
    path: str,
    *,
    actor: str | None,
    is_async: bool,
) -> GeneratedModule:
    """Both pipelines side by side, then the module.

    Raises :class:`CodegenError` on a generation failure (every error
    collected), `PetrinetDslError` on a compile error, `NetValidationError`
    on a parse error.
    """
    text = read_petrinet_text(path)
    source_name = _base_name(path)
    lowered = lower_petrinet_text(text, source_name)
    net = parse_net(compile_petrinet_text(text, source_name))
    return generate_module(
        net,
        source=path.replace("\\", "/"),
        source_name=source_name,
        text=text,
        contributions=lowered["contributions"],
        actor=actor,
        is_async=is_async,
    )


def generate_composition_cli(
    path: str,
    *,
    actor: str | None,
    is_async: bool,
    members_package: str | None,
) -> dict[tuple[str, str], str]:
    """The composition's pipelines: `{output_path: text}` for writing and
    for `--check`.

    The composition module writes beside the composition file; every
    member module beside its own file (the composition module imports
    them by one scheme: `from <stem>_net import ...`, or
    `from <package>.<stem> import ...` under `--members-package`). The
    keys carry the stem so `--out` relocates only the composition
    module's entry.
    """
    from velocitron_codegen import generate_composition_full

    full = generate_composition_full(
        path, actor=actor, is_async=is_async, members_package=members_package
    )
    targets: dict[tuple[str, str], str] = {}
    for key, (text, target_dir) in full.items():
        stem = key.rsplit(".", 1)[-1]
        targets[(str(Path(target_dir) / f"{stem}_net.py"), stem)] = text
    return targets


def document_kind(path: str) -> str:
    return lower_petrinet_text(read_petrinet_text(path), _base_name(path))[
        "documentKind"
    ]


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:  # pyright: ignore[reportPrivateUsage]
    parser = commands.add_parser(
        "codegen",
        help="generate one Python base class per leaf net (ADR 0058)",
        description=(
            "Generate a Python module from a leaf .petrinet: one abstract "
            "base class extending velocitron_netbase.VelocitronNet, abstract "
            "fire_<t> methods for the transitions with a handler fact, "
            "generated concrete handlers for the rest (the arcs' data / data "
            "cel, else the carry rule), abstract guard_<t> and "
            "predicate_<p> methods. From a composition .petrinet it also "
            "generates every nested composition class: <Name>Composition "
            "with one member instance per alias, build_registry(merged_net), "
            "register_members, one typing.Protocol and one RefinedAway mixin "
            "per refined set. --actor NAME removes the transitions another "
            "actor owns; --async emits Runtime methods that take context: "
            "RuntimeContext; --out PATH names the file (default <stem>_net.py "
            "beside FILE; a composition writes every member module too); "
            "--members-package PKG names the package member module imports "
            "come from (default: the sibling spelling from <stem>_net "
            "import ...); --check regenerates everything, compares byte for "
            "byte, and exits 1 with a unified diff on stderr when any file "
            "in place differs or is missing, writing nothing."
        ),
    )
    parser.add_argument(
        "input", metavar="FILE", help="a leaf or composition .petrinet file"
    )
    parser.add_argument(
        "--actor",
        metavar="NAME",
        help="the system the module is for; the flag only ever removes",
    )
    parser.add_argument(
        "--async",
        dest="is_async",
        action="store_true",
        help="emit async def fire_<t>(..., *, context: RuntimeContext)",
    )
    parser.add_argument(
        "--members-package",
        dest="members_package",
        metavar="PKG",
        default=None,
        help="the member module imports' package (default: sibling files)",
    )
    parser.add_argument(
        "--out",
        metavar="PATH",
        help="where to write (default: <stem>_net.py beside FILE)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="regenerate and compare with the file; exit 1 on a difference",
    )


def main(args: argparse.Namespace) -> int:
    path = str(args.input)
    try:
        kind = document_kind(path)
        if kind == "composition":
            targets = generate_composition_cli(
                path,
                actor=args.actor,
                is_async=bool(args.is_async),
                members_package=args.members_package,
            )
            return _compare_or_write_composition(
                path,
                targets,
                check=bool(args.check),
                out=str(args.out) if args.out else None,
            )
        module = generate(path, actor=args.actor, is_async=bool(args.is_async))
    except CodegenError as error:
        for message in error.messages:
            sys.stderr.write(f"{message}\n")
        return 1
    except PetrinetDslError as error:
        sys.stderr.write(error.diagnostic.render() + "\n")
        return 1
    except (OSError, UnicodeError, NetValidationError) as error:
        sys.stderr.write(f"{path}:1:1: error[PN200]: {error}\n")
        return 1
    out = _output_path(path, args.out)
    if getattr(args, "check", False):
        return _compare_one(out, module.text, path)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as handle:
        handle.write(module.text)
    return 0


def _compare_one(out: str, text: str, path: str) -> int:
    target = Path(out)
    if not target.is_file():
        sys.stderr.write(
            f"{out}: missing; run `velocitron codegen {path}` to write it\n"
        )
        return 1
    on_disk = target.read_text(encoding="utf-8")
    if on_disk == text:
        return 0
    diff = "".join(
        difflib.unified_diff(
            on_disk.splitlines(keepends=True),
            text.splitlines(keepends=True),
            fromfile=out,
            tofile=f"{out} (generated)",
        )
    )
    sys.stderr.write(diff)
    return 1


def _compare_or_write_composition(
    path: str,
    targets: dict[tuple[str, str], str],
    *,
    check: bool,
    out: str | None,
) -> int:
    """Write (or check) the composition's every module.

    `--out` relocates the COMPOSITION module; member modules stay beside
    their own files even then.
    """
    composition_stem = Path(path).name.removesuffix(".petrinet").replace("-", "_")
    diffs: list[str] = []
    for (target_path, stem), text in sorted(targets.items()):
        target = Path(target_path)
        if stem == composition_stem and out:
            target = Path(out)
        if check:
            if not target.is_file():
                sys.stderr.write(
                    f"{target}: missing; run `velocitron codegen {path}` to "
                    "write every module\n"
                )
                return 1
            on_disk = target.read_text(encoding="utf-8")
            if on_disk != text:
                diffs.append(
                    "".join(
                        difflib.unified_diff(
                            on_disk.splitlines(keepends=True),
                            text.splitlines(keepends=True),
                            fromfile=str(target),
                            tofile=f"{target} (generated)",
                        )
                    )
                )
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(text)
    if check and diffs:
        for diff in diffs:
            sys.stderr.write(diff)
        return 1
    return 0


__all__ = ["add_parser", "generate", "main"]

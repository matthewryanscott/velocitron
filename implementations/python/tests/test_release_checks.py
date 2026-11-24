from __future__ import annotations

import importlib.util
import json
import stat
import sys
import tarfile
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol, cast

import pytest

_REPOSITORY_ROOT = Path(__file__).parents[3]
_TOOL_PATH = _REPOSITORY_ROOT / "tools" / "release_checks.py"
_SPEC = importlib.util.spec_from_file_location("release_checks", _TOOL_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_RELEASE_CHECKS_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_RELEASE_CHECKS_MODULE)


class _ReleaseChecksTool(Protocol):
    ReleaseCheckError: type[ValueError]

    def inspect_artifacts(
        self, root: Path, allowlist_path: Path, *, version: str, repository: str
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]: ...

    def run_consumers(
        self,
        root: Path,
        *,
        version: str,
        python_version: str,
        uv: str,
        node: str,
        npm: str,
    ) -> tuple[list[dict[str, Any]], dict[str, str]]: ...

    def create_evidence(
        self,
        root: Path,
        allowlist_path: Path,
        *,
        repository: str,
        tag: str,
        tag_ref: str,
        commit: str,
        version: str,
        run_id: int,
        python_version: str,
        uv: str,
        node: str,
        npm: str,
    ) -> dict[str, Any]: ...

    def _audit_browser_seam(
        self,
        package_roots: dict[str, Path],
        node_builtins: set[str],
        *,
        suffixes: tuple[str, ...] = (".js",),
    ) -> dict[str, int]: ...
    def _audit_source_browser_seam(self, *, node: str) -> dict[str, int]: ...
    def main(self) -> int: ...
    def _wrong_repository_identities(self, content: bytes) -> list[str]: ...


_TOOL = cast(_ReleaseChecksTool, cast(object, _RELEASE_CHECKS_MODULE))
_VERSION = "0.1.0"
_REPOSITORY = "circuitmeridian/velocitron"
_REPOSITORY_URL = f"https://github.com/{_REPOSITORY}"
_KINDS = ("python-wheel", "python-sdist")
_PATHS = {
    "python-wheel": f"python/velocitron_cli-{_VERSION}-py3-none-any.whl",
    "python-sdist": f"python/velocitron_cli-{_VERSION}.tar.gz",
}
_PACKAGE_NAMES = {
    "python-wheel": "velocitron-cli",
    "python-sdist": "velocitron-cli",
}
_FILES = {
    "python-wheel": [
        f"velocitron_cli-{_VERSION}.dist-info/METADATA",
        "velocitron_cli/zz-archive-scan-fixture.txt",
    ],
    "python-sdist": [
        f"velocitron_cli-{_VERSION}/PKG-INFO",
        f"velocitron_cli-{_VERSION}/pyproject.toml",
        f"velocitron_cli-{_VERSION}/zz-archive-scan-fixture.txt",
    ],
}


def _python_metadata(name: str, version: str) -> bytes:
    return (
        f"Metadata-Version: 2.1\n"
        f"Name: {name}\n"
        f"Version: {version}\n"
        f"Project-URL: Homepage, {_REPOSITORY_URL}\n"
        f"Project-URL: Repository, {_REPOSITORY_URL}\n"
        f"Project-URL: Issues, {_REPOSITORY_URL}/issues\n"
    ).encode()


def _members(
    kind: str,
    *,
    package_name: str | None = None,
    package_version: str = _VERSION,
    pyproject_version: str = _VERSION,
) -> list[tuple[str, bytes]]:
    name = package_name or _PACKAGE_NAMES[kind]
    if kind == "python-wheel":
        return [
            (_FILES[kind][0], _python_metadata(name, package_version)),
            (_FILES[kind][1], b"ordinary package payload\n"),
        ]
    if kind == "python-sdist":
        return [
            (_FILES[kind][0], _python_metadata(name, package_version)),
            (
                _FILES[kind][1],
                (
                    f'[project]\nname = "velocitron-cli"\n'
                    f'version = "{pyproject_version}"\n'
                    f'[project.urls]\nHomepage = "{_REPOSITORY_URL}"\n'
                    f'Repository = "{_REPOSITORY_URL}"\n'
                    f'Issues = "{_REPOSITORY_URL}/issues"\n'
                ).encode(),
            ),
            (_FILES[kind][2], b"ordinary package payload\n"),
        ]
    raise AssertionError(kind)


def _write_archive(
    root: Path,
    kind: str,
    members: list[tuple[str, bytes]],
    *,
    non_regular: tuple[str, str] | None = None,
) -> None:
    path = root / _PATHS[kind]
    path.parent.mkdir(parents=True, exist_ok=True)
    if kind == "python-wheel":
        with zipfile.ZipFile(path, "w") as archive:
            for name, content in members:
                if non_regular is not None and name == non_regular[0]:
                    info = zipfile.ZipInfo(name)
                    info.create_system = 3
                    mode = stat.S_IFLNK if non_regular[1] == "symlink" else stat.S_IFIFO
                    info.external_attr = (mode | 0o777) << 16
                    archive.writestr(info, b"target")
                else:
                    archive.writestr(name, content)
        return

    with tarfile.open(path, "w:gz") as archive:
        for name, content in members:
            info = tarfile.TarInfo(name)
            if non_regular is not None and name == non_regular[0]:
                info.type = (
                    tarfile.SYMTYPE if non_regular[1] == "symlink" else tarfile.FIFOTYPE
                )
                info.linkname = "target" if non_regular[1] == "symlink" else ""
            else:
                info.size = len(content)
                archive.addfile(info, BytesIO(content))
                continue
            archive.addfile(info)


def _write_allowlist(root: Path, *, version: str = _VERSION) -> Path:
    path = root / "release-allowlist.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "version": version,
                "artifacts": [
                    {
                        "kind": kind,
                        "format": "zip" if kind == "python-wheel" else "tar-gz",
                        "packageName": _PACKAGE_NAMES[kind],
                        "path": _PATHS[kind],
                        "files": _FILES[kind],
                    }
                    for kind in _KINDS
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_candidate(root: Path, *, allowlist_version: str = _VERSION) -> Path:
    for kind in _KINDS:
        _write_archive(root, kind, _members(kind))
    return _write_allowlist(root, version=allowlist_version)


def test_exact_archive_members_and_package_metadata_pass(tmp_path: Path) -> None:
    # given: two minimal packages whose members exactly match the release allowlist
    allowlist_path = _write_candidate(tmp_path)

    # when: the package archives are inspected without running any consumers
    records, allowlist = _TOOL.inspect_artifacts(
        tmp_path, allowlist_path, version=_VERSION, repository=_REPOSITORY
    )

    # then: each package identity and exact member count is recorded
    assert [
        (record["kind"], record["metadata"]["name"], record["metadata"]["version"])
        for record in records
    ] == [
        ("python-wheel", "velocitron-cli", _VERSION),
        ("python-sdist", "velocitron-cli", _VERSION),
    ]
    assert allowlist["path"] == allowlist_path.name
    assert allowlist["artifactMemberCounts"] == {
        kind: len(_FILES[kind]) for kind in _KINDS
    }


@pytest.mark.parametrize(
    ("kind", "mangle"),
    [
        ("python-wheel", lambda files: list(reversed(files))),
        ("python-sdist", lambda files: [files[0], *files]),
    ],
)
def test_allowlist_files_unsorted_or_duplicated_fail(
    tmp_path: Path, kind: str, mangle: Any
) -> None:
    # given: a candidate allowlist whose files list is out of order or duplicated
    allowlist_path = _write_candidate(tmp_path)
    document = json.loads(allowlist_path.read_text(encoding="utf-8"))
    artifact = next(item for item in document["artifacts"] if item["kind"] == kind)
    artifact["files"] = mangle(artifact["files"])
    allowlist_path.write_text(json.dumps(document), encoding="utf-8")

    # when/then: inspection rejects the allowlist before touching the archives
    with pytest.raises(_TOOL.ReleaseCheckError, match="must be unique and sorted"):
        _TOOL.inspect_artifacts(
            tmp_path, allowlist_path, version=_VERSION, repository=_REPOSITORY
        )


@pytest.mark.parametrize("kind", _KINDS)
def test_extra_archive_member_fails(tmp_path: Path, kind: str) -> None:
    # given: an otherwise exact package archive containing one unallowlisted file
    allowlist_path = _write_candidate(tmp_path)
    _write_archive(tmp_path, kind, [*_members(kind), ("unexpected.txt", b"extra")])

    # when/then: exact-set inspection rejects the unexpected member
    with pytest.raises(_TOOL.ReleaseCheckError, match="unexpected=.*unexpected.txt"):
        _TOOL.inspect_artifacts(
            tmp_path, allowlist_path, version=_VERSION, repository=_REPOSITORY
        )


@pytest.mark.parametrize("kind", _KINDS)
def test_missing_archive_member_fails(tmp_path: Path, kind: str) -> None:
    # given: a package archive missing one allowlisted file
    allowlist_path = _write_candidate(tmp_path)
    _write_archive(tmp_path, kind, _members(kind)[:-1])

    # when/then: exact-set inspection rejects the missing member
    with pytest.raises(
        _TOOL.ReleaseCheckError, match="archive file set differs: missing="
    ):
        _TOOL.inspect_artifacts(
            tmp_path, allowlist_path, version=_VERSION, repository=_REPOSITORY
        )


@pytest.mark.parametrize("kind", _KINDS)
def test_unsafe_traversal_member_fails(tmp_path: Path, kind: str) -> None:
    # given: an otherwise exact archive with a parent-directory traversal member
    allowlist_path = _write_candidate(tmp_path)
    _write_archive(tmp_path, kind, [*_members(kind), ("../escape", b"unsafe")])

    # when/then: inspection rejects the unsafe path before considering its contents
    with pytest.raises(_TOOL.ReleaseCheckError, match="unsafe archive member path"):
        _TOOL.inspect_artifacts(
            tmp_path, allowlist_path, version=_VERSION, repository=_REPOSITORY
        )


@pytest.mark.parametrize("kind", _KINDS)
def test_duplicate_archive_member_fails(tmp_path: Path, kind: str) -> None:
    # given: an archive containing the same required member twice
    allowlist_path = _write_candidate(tmp_path)
    members = _members(kind)
    if kind == "python-wheel":
        with pytest.warns(UserWarning, match="Duplicate name"):
            _write_archive(tmp_path, kind, [*members, members[0]])
    else:
        _write_archive(tmp_path, kind, [*members, members[0]])

    # when/then: inspection rejects the duplicate even though its set is allowlisted
    with pytest.raises(_TOOL.ReleaseCheckError, match="archive has duplicate member"):
        _TOOL.inspect_artifacts(
            tmp_path, allowlist_path, version=_VERSION, repository=_REPOSITORY
        )


@pytest.mark.parametrize(
    ("kind", "member_type"),
    [
        ("python-wheel", "symlink"),
        ("python-sdist", "fifo"),
    ],
)
def test_non_regular_archive_member_fails(
    tmp_path: Path, kind: str, member_type: str
) -> None:
    # given: a required archive member encoded as a symlink or other non-regular type
    allowlist_path = _write_candidate(tmp_path)
    members = _members(kind)
    _write_archive(
        tmp_path,
        kind,
        members,
        non_regular=(members[0][0], member_type),
    )

    # when/then: inspection refuses to treat the special entry as package content
    with pytest.raises(_TOOL.ReleaseCheckError, match="archive has non-regular member"):
        _TOOL.inspect_artifacts(
            tmp_path, allowlist_path, version=_VERSION, repository=_REPOSITORY
        )


def test_release_artifact_symlink_fails(tmp_path: Path) -> None:
    # given: an allowlisted artifact path that redirects to a regular archive by symlink
    allowlist_path = _write_candidate(tmp_path)
    artifact_path = tmp_path / _PATHS["python-wheel"]
    target = tmp_path / "real.whl"
    artifact_path.replace(target)
    artifact_path.symlink_to(target)

    # when/then: inspection requires the release artifact itself to be regular
    with pytest.raises(
        _TOOL.ReleaseCheckError, match="missing regular release artifact"
    ):
        _TOOL.inspect_artifacts(
            tmp_path, allowlist_path, version=_VERSION, repository=_REPOSITORY
        )


@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize("field", ["name", "version"])
def test_wrong_package_metadata_identity_fails(
    tmp_path: Path, kind: str, field: str
) -> None:
    # given: an exact archive whose embedded package identity is not the candidate identity
    allowlist_path = _write_candidate(tmp_path)
    members = _members(
        kind,
        package_name="wrong-package" if field == "name" else None,
        package_version="9.9.9" if field == "version" else _VERSION,
    )
    _write_archive(tmp_path, kind, members)

    # when/then: inspection rejects the wrong embedded name or version
    with pytest.raises(_TOOL.ReleaseCheckError, match="metadata identity differs"):
        _TOOL.inspect_artifacts(
            tmp_path, allowlist_path, version=_VERSION, repository=_REPOSITORY
        )


def _synthetic_wrong_identities() -> tuple[bytes, ...]:
    owner = b"wrong-owner"
    repository = b"velocitron"
    slug = owner + b"/" + repository
    return (
        b"https://GITHUB.com/" + slug,
        b"git+https://github.com/" + slug + b".git",
        b"ssh://git@GitHub.com/" + slug + b".git",
        b"git@GITHUB.com:" + slug + b".git",
        slug,
    )


def test_every_allowlisted_archive_member_rejects_wrong_repository_identity(
    tmp_path: Path,
) -> None:
    # given: each regular member of every archive type, including non-metadata payloads
    wrong_identities = _synthetic_wrong_identities()
    allowlist_path = _write_candidate(tmp_path)

    # when/then: the generic identity scan checks every allowlisted member body
    for kind in _KINDS:
        original = _members(kind)
        for index, (name, _) in enumerate(original):
            members = list(original)
            members[index] = (
                name,
                b"payload " + wrong_identities[index % len(wrong_identities)],
            )
            _write_archive(tmp_path, kind, members)
            with pytest.raises(
                _TOOL.ReleaseCheckError, match="wrong repository identity"
            ):
                _TOOL.inspect_artifacts(
                    tmp_path,
                    allowlist_path,
                    version=_VERSION,
                    repository=_REPOSITORY,
                )


def test_wrong_repository_detector_covers_supported_git_forms() -> None:
    # given: synthetic wrong-owner references in every accepted GitHub spelling
    identities = _synthetic_wrong_identities()

    # when/then: host case and transport cannot bypass owner binding
    for identity in identities:
        assert _TOOL._wrong_repository_identities(  # pyright: ignore[reportPrivateUsage]
            identity
        ) == [identity.decode("ascii")]


def test_repository_detector_accepts_circuit_meridian_git_forms() -> None:
    # given: the approved owner under every supported GitHub transport
    identities = (
        b"https://GITHUB.com/circuitmeridian/velocitron",
        b"git+https://github.com/circuitmeridian/velocitron.git",
        b"ssh://git@GitHub.com/circuitmeridian/velocitron.git",
        b"git@GITHUB.com:circuitmeridian/velocitron.git",
        b"circuitmeridian/velocitron",
    )

    # when/then: generic detection does not reject the canonical repository
    for identity in identities:
        assert (
            _TOOL._wrong_repository_identities(  # pyright: ignore[reportPrivateUsage]
                identity
            )
            == []
        )


@pytest.mark.parametrize("kind", _KINDS)
def test_wrong_organization_repository_url_in_metadata_fails(
    tmp_path: Path, kind: str
) -> None:
    # given: package metadata naming a syntactically valid but unapproved organization
    allowlist_path = _write_candidate(tmp_path)
    wrong_url = _synthetic_wrong_identities()[0]
    members = [
        (name, content.replace(_REPOSITORY_URL.encode(), wrong_url))
        for name, content in _members(kind)
    ]
    _write_archive(tmp_path, kind, members)

    # when/then: exact metadata assertions bind archives to Circuit Meridian
    with pytest.raises(_TOOL.ReleaseCheckError, match="wrong repository identity"):
        _TOOL.inspect_artifacts(
            tmp_path,
            allowlist_path,
            version=_VERSION,
            repository=_REPOSITORY,
        )


def test_wrong_sdist_pyproject_version_fails(tmp_path: Path) -> None:
    # given: an exact sdist whose pyproject version disagrees with its valid PKG-INFO
    allowlist_path = _write_candidate(tmp_path)
    _write_archive(
        tmp_path,
        "python-sdist",
        _members("python-sdist", pyproject_version="9.9.9"),
    )

    # when/then: inspection rejects the conflicting build metadata version
    with pytest.raises(_TOOL.ReleaseCheckError, match="pyproject version differs"):
        _TOOL.inspect_artifacts(
            tmp_path, allowlist_path, version=_VERSION, repository=_REPOSITORY
        )


def test_wrong_allowlist_version_fails(tmp_path: Path) -> None:
    # given: valid candidate archives paired with an allowlist for another version
    allowlist_path = _write_candidate(tmp_path, allowlist_version="9.9.9")

    # when/then: inspection rejects an allowlist not bound to the candidate version
    with pytest.raises(_TOOL.ReleaseCheckError, match="allowlist schema or version"):
        _TOOL.inspect_artifacts(
            tmp_path, allowlist_path, version=_VERSION, repository=_REPOSITORY
        )


def test_special_mode_wheel_directory_fails(tmp_path: Path) -> None:
    # given: an expected wheel directory entry whose Unix mode encodes a symlink
    allowlist_path = _write_candidate(tmp_path)
    wheel_path = tmp_path / _PATHS["python-wheel"]
    directory = zipfile.ZipInfo(f"velocitron_cli-{_VERSION}.dist-info/")
    directory.create_system = 3
    directory.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(wheel_path, "a") as archive:
        archive.writestr(directory, b"target")

    # when/then: a trailing slash cannot bypass the special-file rejection
    with pytest.raises(_TOOL.ReleaseCheckError, match="archive has non-regular member"):
        _TOOL.inspect_artifacts(
            tmp_path, allowlist_path, version=_VERSION, repository=_REPOSITORY
        )


def test_browser_audit_rejects_runtime_node_builtin(
    tmp_path: Path,
) -> None:
    # given: packed browser JavaScript importing a builtin outside a handwritten shortlist
    source_root = tmp_path / "package" / "dist"
    source_root.mkdir(parents=True)
    (source_root / "index.js").write_text(
        'import channel from "diagnostics_channel";\n', encoding="utf-8"
    )

    # when/then: the runtime-provided builtin inventory rejects the import
    with pytest.raises(_TOOL.ReleaseCheckError, match="Node builtin import"):
        _TOOL._audit_browser_seam(  # pyright: ignore[reportPrivateUsage]
            {"package": source_root}, {"diagnostics_channel"}
        )


def test_browser_audit_enforces_shared_inventory_tokens_in_typescript(
    tmp_path: Path,
) -> None:
    # given: TypeScript source carrying a forbidden token from the shared inventory
    source_root = tmp_path / "src"
    source_root.mkdir()
    (source_root / "backend.ts").write_text(
        "export const build = (source: string): unknown => new Function(source);\n",
        encoding="utf-8",
    )

    # when/then: the source-suffix audit rejects the token loaded from the inventory
    with pytest.raises(
        _TOOL.ReleaseCheckError, match="browser seam rejected dynamic Function"
    ):
        _TOOL._audit_browser_seam(  # pyright: ignore[reportPrivateUsage]
            {"package": source_root}, {"fs"}, suffixes=(".js", ".ts")
        )


def test_browser_audit_scans_typescript_suffix_for_source_tree(tmp_path: Path) -> None:
    # given: clean TypeScript source and a sibling non-source file
    source_root = tmp_path / "src"
    source_root.mkdir()
    (source_root / "index.ts").write_text(
        "export type Answer = 42;\n", encoding="utf-8"
    )
    (source_root / "README.md").write_text("danger: eval\\(\\)\n", encoding="utf-8")

    # when: the audit runs with the source-tree suffix set
    counts = _TOOL._audit_browser_seam(  # pyright: ignore[reportPrivateUsage]
        {"package": source_root}, {"fs"}, suffixes=(".js", ".ts")
    )

    # then: only the source suffixes are scanned and counted
    assert counts == {"package": 1}


def test_source_tree_browser_seam_audit_targets_source_roots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # given: the consolidated auditor is the only seam-audit implementation
    audits: list[tuple[dict[str, Path], tuple[str, ...], set[str]]] = []

    def fake_audit(
        package_roots: dict[str, Path],
        node_builtins: set[str],
        *,
        suffixes: tuple[str, ...] = (".js",),
    ) -> dict[str, int]:
        audits.append((dict(package_roots), suffixes, node_builtins))
        return {name: 1 for name in package_roots}

    def fake_run(
        command: list[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> str:
        assert cwd is None and env is not None
        assert command[:3] == ["node", "--input-type=module", "-e"]
        return json.dumps(["fs"])

    monkeypatch.setattr(_RELEASE_CHECKS_MODULE, "_audit_browser_seam", fake_audit)
    monkeypatch.setattr(_RELEASE_CHECKS_MODULE, "_run", fake_run)

    # when: the source-tree lifetime point runs the consolidated auditor
    counts = _TOOL._audit_source_browser_seam(  # pyright: ignore[reportPrivateUsage]
        node="node"
    )

    # then: it audits the leaf packages and the CEL backend
    assert set(counts) == {
        "@velocitron/cel",
        "@velocitron/dsl",
        "@velocitron/engine",
        "@velocitron/merge",
        "@velocitron/petrinet",
        "@velocitron/runtime",
        "@velocitron/analysis",
        "@velocitron/properties",
        "@velocitron/explain",
        "@velocitron/equiv",
        "@velocitron/codegen",
        "@velocitron/netbase",
        "@velocitron/replay",
        "@velocitron/cli",
        "@marcbachmann/cel-js",
    }
    package_roots, suffixes, node_builtins = audits[0]
    assert suffixes == (".js", ".ts")
    assert node_builtins == {"fs"}
    assert package_roots["@velocitron/cel"].parts[-3:] == (
        "cel",
        "typescript",
        "src",
    )
    assert package_roots["@velocitron/dsl"].parts[-3:] == (
        "dsl",
        "typescript",
        "src",
    )
    assert package_roots["@velocitron/engine"].parts[-3:] == (
        "engine",
        "typescript",
        "src",
    )
    assert package_roots["@velocitron/merge"].parts[-3:] == (
        "merge",
        "typescript",
        "src",
    )
    assert package_roots["@velocitron/petrinet"].parts[-3:] == (
        "petrinet",
        "typescript",
        "src",
    )
    assert package_roots["@velocitron/runtime"].parts[-3:] == (
        "runtime",
        "typescript",
        "src",
    )
    assert package_roots["@velocitron/analysis"].parts[-3:] == (
        "analysis",
        "typescript",
        "src",
    )
    assert package_roots["@velocitron/properties"].parts[-3:] == (
        "properties",
        "typescript",
        "src",
    )
    assert package_roots["@velocitron/explain"].parts[-3:] == (
        "explain",
        "typescript",
        "src",
    )
    assert package_roots["@velocitron/equiv"].parts[-3:] == (
        "equiv",
        "typescript",
        "src",
    )
    assert package_roots["@velocitron/codegen"].parts[-3:] == (
        "codegen",
        "typescript",
        "src",
    )
    assert package_roots["@velocitron/netbase"].parts[-3:] == (
        "netbase",
        "typescript",
        "src",
    )
    assert package_roots["@velocitron/replay"].parts[-3:] == (
        "replay",
        "typescript",
        "src",
    )
    assert package_roots["@velocitron/cli"].parts[-3:] == (
        "cli",
        "typescript",
        "src",
    )
    assert package_roots["@marcbachmann/cel-js"].parts[-4:] == (
        "node_modules",
        "@marcbachmann",
        "cel-js",
        "lib",
    )


def test_source_browser_seam_cli_mode_without_release_flags(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # given: the source-tree audit mode invoked without release-artifact flags
    def fake_audit(*, node: str) -> dict[str, int]:
        assert node == "node"
        return {"@velocitron/core": 12, "@marcbachmann/cel-js": 3}

    monkeypatch.setattr(
        _RELEASE_CHECKS_MODULE, "_audit_source_browser_seam", fake_audit
    )
    monkeypatch.setattr(
        sys, "argv", ["release_checks.py", "--audit-source-browser-seam"]
    )

    # when/then: the mode reports a clean seam and skips release verification
    assert _TOOL.main() == 0
    assert "Browser seam is clean" in capsys.readouterr().out


def test_release_verification_mode_still_demands_release_flags(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # given: neither source-audit mode nor release flags on the command line
    monkeypatch.setattr(sys, "argv", ["release_checks.py"])

    # when/then: the consolidated parser demands the release verification flags
    with pytest.raises(SystemExit):
        _TOOL.main()
    assert "release verification requires" in capsys.readouterr().err


def test_clean_consumer_coordination_covers_every_installation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # given: controlled command seams for the Python consumer environments
    release_root = tmp_path / "release"
    for relative in _PATHS.values():
        artifact = release_root / relative
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(b"artifact")
    audited_builtins: list[set[str]] = []

    def fake_create_venv(_uv: str, _python_version: str, environment: Path) -> Path:
        python = environment / "bin" / "python"
        python.parent.mkdir(parents=True)
        python.write_text("", encoding="utf-8")
        return python

    def fake_run(
        command: list[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> str:
        del env
        if command[:3] == ["node", "--input-type=module", "-e"]:
            if "builtinModules" in command[3]:
                return json.dumps(["fs", "diagnostics_channel"])
            return ""
        if command == ["node", "--version"]:
            return "v24.15.0"
        if command == ["npm", "--version"]:
            return "11.12.1"
        if command == ["uv", "--version"]:
            return "uv 0.11.29"
        return ""

    def fake_core(
        _python: Path, _environment: Path, *, version: str
    ) -> dict[str, object]:
        assert version == _VERSION
        return {"celBackend": "CelpyAdapter", "checks": ["core"]}

    def fake_extra(
        _python: Path, *, version: str, class_name: str
    ) -> dict[str, object]:
        assert version == _VERSION
        return {"celBackend": class_name, "checks": ["extra"]}

    def fake_audit(_roots: dict[str, Path], builtins: set[str]) -> dict[str, int]:
        audited_builtins.append(builtins)
        return {"@velocitron/core": 1, "@marcbachmann/cel-js": 1}

    def fake_install_python(
        uv: str,
        python: Path,
        artifact: Path,
        *,
        extra: str | None = None,
    ) -> None:
        del uv, python, artifact, extra

    monkeypatch.setattr(_RELEASE_CHECKS_MODULE, "_create_venv", fake_create_venv)
    monkeypatch.setattr(_RELEASE_CHECKS_MODULE, "_install_python", fake_install_python)
    monkeypatch.setattr(_RELEASE_CHECKS_MODULE, "_exercise_python_core", fake_core)
    monkeypatch.setattr(_RELEASE_CHECKS_MODULE, "_exercise_python_extra", fake_extra)
    monkeypatch.setattr(_RELEASE_CHECKS_MODULE, "_audit_browser_seam", fake_audit)
    monkeypatch.setattr(_RELEASE_CHECKS_MODULE, "_run", fake_run)

    # when: clean-consumer coordination runs against exact artifact paths
    consumers, toolchain = _TOOL.run_consumers(
        release_root,
        version=_VERSION,
        python_version="3.12.11",
        uv="uv",
        node="node",
        npm="npm",
    )

    # then: wheel core, sdist core, and both wheel extras bite
    assert [
        (consumer["artifact"], consumer["installation"]) for consumer in consumers
    ] == [
        ("python-wheel", "core"),
        ("python-sdist", "core"),
        ("python-wheel", "cel-cpp"),
        ("python-wheel", "cel-rust"),
    ]
    assert audited_builtins == []
    # and: the evidence records the actual clean-consumer tool versions
    assert toolchain["node"] == "24.15.0"
    assert toolchain["npm"] == "11.12.1"
    assert toolchain["uv"] == "uv 0.11.29"


def test_evidence_schema_binds_identity_hashes_and_consumer_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # given: inspected artifacts and completed consumers with deterministic records
    artifact = {
        "kind": "python-wheel",
        "path": _PATHS["python-wheel"],
        "sha256": "c" * 64,
        "size": 123,
        "memberCount": 1,
        "metadata": {"name": "velocitron-cli", "version": _VERSION},
    }
    allowlist = {
        "path": "release-allowlist.json",
        "sha256": "d" * 64,
        "artifactMemberCounts": {"python-wheel": 1},
    }
    consumers = [{"artifact": "python-wheel", "installation": "core"}]
    toolchain = {"node": "24.15.0"}

    def fake_inspect(
        root: Path, allowlist_path: Path, *, version: str, repository: str
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        del root, allowlist_path, version, repository
        return [artifact], allowlist

    def fake_consumers(
        root: Path,
        *,
        version: str,
        python_version: str,
        uv: str,
        node: str,
        npm: str,
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        del root, version, python_version, uv, node, npm
        return consumers, toolchain

    monkeypatch.setattr(
        _RELEASE_CHECKS_MODULE,
        "inspect_artifacts",
        fake_inspect,
    )
    monkeypatch.setattr(
        _RELEASE_CHECKS_MODULE,
        "run_consumers",
        fake_consumers,
    )

    # when: the release evidence is assembled
    evidence = _TOOL.create_evidence(
        tmp_path,
        tmp_path / "allowlist.json",
        repository=_REPOSITORY,
        tag=f"v{_VERSION}",
        tag_ref="a" * 40,
        commit="b" * 40,
        version=_VERSION,
        run_id=1234,
        python_version="3.12.11",
        uv="uv",
        node="node",
        npm="npm",
    )

    # then: identity, allowlist digest, artifact digest, consumers, and versions survive
    assert evidence == {
        "schemaVersion": 1,
        "source": {
            "repository": _REPOSITORY,
            "tag": f"v{_VERSION}",
            "tagRef": "a" * 40,
            "commit": "b" * 40,
            "runId": 1234,
            "version": _VERSION,
        },
        "allowlist": allowlist,
        "artifacts": [artifact],
        "consumers": consumers,
        "toolchain": toolchain,
    }

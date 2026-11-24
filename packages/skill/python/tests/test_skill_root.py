"""``skill_root`` reads the one authoring tree shipped as package data."""

from __future__ import annotations

from pathlib import Path

from velocitron_skill import skill_root

_REPO_SKILL = Path(__file__).resolve().parents[4] / "skills" / "velocitron"
_PACKAGE_LINK = (
    Path(__file__).resolve().parents[1] / "src" / "velocitron_skill" / "skill"
)


def test_the_package_symlinks_the_authoring_tree() -> None:
    # given: the skill package's data link
    # then: the link target is the repo skill tree
    assert _PACKAGE_LINK.is_symlink()
    assert _PACKAGE_LINK.resolve() == _REPO_SKILL.resolve()
    assert (_REPO_SKILL / "SKILL.md").is_file()


def test_skill_root_is_package_data_with_the_authoring_bytes() -> None:
    # when: the installed package resolves the bundled skill
    resolved = skill_root()

    # then: the path is package data named skill, and the bytes are the tree's
    assert resolved.name == "skill"
    assert resolved.parent.name == "velocitron_skill"
    assert resolved.parent.name != "skills"
    assert (resolved / "SKILL.md").read_bytes() == (
        _REPO_SKILL / "SKILL.md"
    ).read_bytes()
    assert (resolved / "scripts" / "cli-help.sh").is_file()
    assert (resolved / "kitchen-sink.petrinet").is_file()

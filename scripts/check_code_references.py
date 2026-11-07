#!/usr/bin/env python3
"""Checks that what a skill names in Awake Core still exists there.

A skill that describes code which moved or was renamed sends agents the wrong way. This reads every
SKILL.md and references/*.md in the bundle and checks three kinds of reference against a Core checkout:

- Gradle module paths, such as `:awake:scene:canvas` or `awake:compose:runtime`;
- repository paths, such as `website/docs/guides/game-ui.md`, written in backticks or as a
  https://github.com/awakekt/awake/blob|tree/<ref>/<path> link;
- type names in inline backticks, such as `CanvasParts` or `SceneCanvas.items`: a capitalised name, with an
  optional `.member`, that Core's Kotlin sources must declare (`class`, `interface`, `object`, `typealias`,
  `fun`, `val`).

A name the skill declares in its own fenced code is an example, not a claim about Core, and is skipped, as is
any name listed in the bundle's `code-references.ignore` (one per line; `#` starts a comment): names from the
Kotlin standard library, AndroidX or kotlinx that a skill mentions on purpose.

Drift that is already known is listed in `code-references.baseline`, one `file: problem` per line, so only new
drift fails; `--write-baseline` rewrites it. Fix a baseline entry by fixing the skill, then drop its line.
Exit status 1 lists every new missing reference, by file and line.

Usage: check_code_references.py --core PATH_TO_AWAKE [--ref origin/main] [--write-baseline] [BUNDLE_DIR]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

INLINE = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
REPO_LINK = re.compile(r"https://github\.com/awakekt/awake/(?:blob|tree)/[^/\s)>]+/([^\s)#?>]+)")
MODULE = re.compile(r"^:?awake(?::[a-z0-9-]+)+$")
PATH = re.compile(r"^(?:awake|website|docs|build-logic|samples|scripts|tools)/[A-Za-z0-9_./-]+$")
TYPE = re.compile(r"^([A-Z][A-Za-z0-9]+)(?:\.([a-z][A-Za-z0-9]*))?(?:\(\))?$")
DECLARED = re.compile(r"\b(?:class|interface|object|typealias|fun|val|var|enum class)\s+(?:<[^>]*>\s*)?([A-Za-z_][A-Za-z0-9_]*)")
FENCE = re.compile(r"^\s*(```|~~~)")


class Core:
    """Answers whether a path, module or declaration exists in a Core checkout at [ref]."""

    def __init__(self, root: Path, ref: str) -> None:
        self.root, self.ref = root, ref
        files = self._git("ls-tree", "-r", "--name-only", ref).splitlines()
        self.files = set(files)
        self.dirs = {str(Path(f).parent) for f in files} | {
            str(p) for f in files for p in Path(f).parents if str(p) != "."
        }
        self._declared: dict[str, bool] = {}

    def _git(self, *args: str) -> str:
        return subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True, check=False).stdout

    def has_path(self, path: str) -> bool:
        path = path.rstrip("/")
        return path in self.files or path in self.dirs

    def has_file_named(self, name: str) -> bool:
        return any(f == name or f.endswith("/" + name) for f in self.files)

    def has_module(self, module: str) -> bool:
        # A module, or a group of modules such as `:awake:compose`.
        return self.has_path(module.lstrip(":").replace(":", "/"))

    def declares(self, name: str) -> bool:
        if name not in self._declared:
            declaration = rf"\b(class|interface|object|typealias|fun|val|var)\s+(<[^>]*>\s*)?([A-Za-z0-9_.]*\.)?{name}\b"
            enum_entry = rf"^\s*{name}\s*([(,;{{]|$)"
            out = self._git("grep", "-E", "-l", "-m1", "-e", declaration, "-e", enum_entry, self.ref, "--", "*.kt", "*.kts")
            self._declared[name] = bool(out.strip())
        return self._declared[name]


def skill_files(bundle: Path) -> list[Path]:
    return sorted([*bundle.glob("skills/*/SKILL.md"), *bundle.glob("skills/*/references/*.md")])


def read_ignored(bundle: Path) -> set[str]:
    file = bundle / "code-references.ignore"
    if not file.is_file():
        return set()
    return {line.split("#", 1)[0].strip() for line in file.read_text().splitlines()} - {""}


def references(text: str) -> tuple[set[str], list[tuple[int, str, bool]]]:
    """The names [text] declares in its fenced code, and each (line, reference, is a link) outside fences."""
    declared: set[str] = set()
    found: list[tuple[int, str, bool]] = []
    in_fence = False
    for number, line in enumerate(text.splitlines(), start=1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            declared.update(DECLARED.findall(line))
            continue
        found.extend((number, ref, False) for ref in INLINE.findall(line))
        found.extend((number, link.rstrip("."), True) for link in REPO_LINK.findall(line))
    return declared, found


def problem(core: Core, ref: str, link: bool, declared: set[str], ignored: set[str]) -> str | None:
    """Why [ref] is stale, or None when it holds or isn't a Core reference this checks."""
    if link:
        return None if core.has_path(ref) else f"repository path {ref} is not in Core"
    token = ref.strip()
    if token in ignored:
        return None
    if MODULE.match(token):
        return None if core.has_module(token) else f"module {token} is not in Core"
    if PATH.match(token):
        if "..." in token or "*" in token or "<" in token:
            return None
        return None if core.has_path(token) else f"path {token} is not in Core"
    match = TYPE.match(token)
    if not match:
        return None
    owner, member = match.group(1), match.group(2)
    if member in ("kt", "kts"):
        name = f"{owner}.{member}"
        return None if core.has_file_named(name) else f"file {name} is not in Core"
    if owner in declared or owner in ignored or len(owner) < 4 or owner.isupper():
        return None
    if not core.declares(owner):
        return f"{owner} is not declared in Core"
    if member and member not in declared and not core.declares(member):
        return f"{owner}.{member}: {member} is not declared in Core"
    return None


def check(bundle: Path, core: Core) -> list[tuple[str, int, str]]:
    """Every stale reference, as (file, line, problem)."""
    ignored = read_ignored(bundle)
    failures = []
    for file in skill_files(bundle):
        declared, found = references(file.read_text())
        for line, ref, link in found:
            why = problem(core, ref, link, declared, ignored)
            if why:
                failures.append((str(file.relative_to(bundle)), line, why))
    return failures


def read_baseline(bundle: Path) -> set[str]:
    file = bundle / "code-references.baseline"
    return set(file.read_text().splitlines()) - {""} if file.is_file() else set()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("bundle", nargs="?", default=".", type=Path)
    parser.add_argument("--core", required=True, type=Path, help="a checkout of awakekt/awake")
    parser.add_argument("--ref", default="HEAD", help="the Core revision to check against")
    parser.add_argument("--write-baseline", action="store_true", help="record today's drift as known")
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    failures = check(bundle, Core(args.core.resolve(), args.ref))
    keys = {f"{file}: {why}" for file, _, why in failures}
    if args.write_baseline:
        (bundle / "code-references.baseline").write_text("".join(f"{key}\n" for key in sorted(keys)))
        print(f"{bundle.name}: recorded {len(keys)} known stale reference(s) in code-references.baseline")
        return 0
    baseline = read_baseline(bundle)
    new = [(file, line, why) for file, line, why in failures if f"{file}: {why}" not in baseline]
    for file, line, why in new:
        print(f"{file}:{line}: {why}")
    fixed = baseline - keys
    if fixed:
        print(f"{bundle.name}: {len(fixed)} baseline entr(ies) no longer stale; remove them from code-references.baseline")
    if new:
        print(f"{bundle.name}: {len(new)} new stale Core reference(s); fix the skill, or list a non-Core name in code-references.ignore")
        return 1
    print(f"{bundle.name}: no new stale Core references at {args.ref} ({len(baseline)} known in the baseline)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

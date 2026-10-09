#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2023-2026 Ron June Valdoz
# SPDX-License-Identifier: Apache-2.0
"""Check an Awake skill bundle against docs/skill-authoring.md. Configured by bundle.toml."""

from __future__ import annotations

import datetime
import re
import sys
import tomllib
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LINK_PATTERN = re.compile(r"\]\(([^)]+)\)")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_LINES = 250


def parse_frontmatter(text: str) -> dict[str, str]:
    """Top-level keys, plus `metadata.<key>` for the nested metadata block."""
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        return {}
    try:
        end = lines.index("---", 1)
    except ValueError:
        return {}
    fields: dict[str, str] = {}
    parent = ""
    index = 1
    while index < end:
        line = lines[index]
        nested = re.match(r"^\s+([a-zA-Z0-9_-]+):\s*(.*)$", line)
        if nested and parent:
            fields[f"{parent}.{nested.group(1)}"] = nested.group(2).strip().strip("\"'")
            index += 1
            continue
        match = re.match(r"^([a-zA-Z0-9_-]+):\s*(.*)$", line)
        if not match:
            index += 1
            continue
        key, value = match.groups()
        parent = key if not value else ""
        if value in {">", ">-", ">+", "|", "|-", "|+"}:
            parent = ""
            parts: list[str] = []
            index += 1
            while index < end and (not lines[index] or lines[index][0].isspace()):
                if lines[index].strip():
                    parts.append(lines[index].strip())
                index += 1
            fields[key] = " ".join(parts)
            continue
        fields[key] = value.strip().strip("\"'")
        index += 1
    return fields


def validate_links(path: Path, text: str, errors: list[str]) -> None:
    for match in LINK_PATTERN.finditer(text):
        target = match.group(1).strip().split(maxsplit=1)[0].strip("<>")
        if not target or target.startswith(("#", "/", "//")) or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
            continue
        local_target = unquote(target.split("#", 1)[0].split("?", 1)[0])
        if not local_target:
            continue
        resolved = (path.parent / local_target).resolve()
        if ROOT not in resolved.parents and resolved != ROOT:
            errors.append(f"{path.relative_to(ROOT)}: relative link escapes the bundle (use a URL): {target}")
        elif not resolved.exists():
            errors.append(f"{path.relative_to(ROOT)}: broken relative link: {target}")


def validate_skill(path: Path, config: dict, errors: list[str]) -> str:
    text = path.read_text(encoding="utf-8")
    relative = path.relative_to(ROOT)
    fields = parse_frontmatter(text)
    if not fields:
        errors.append(f"{relative}: missing or invalid YAML frontmatter")
        return ""
    name = fields.get("name", "")
    namespace = config["namespace"]
    if len(name) > 64 or not NAME_PATTERN.fullmatch(name) or name != path.parent.name:
        errors.append(f"{relative}: name must be lowercase-hyphen (max 64) and match its directory")
    if not (name == namespace or name.startswith(f"{namespace}-")):
        errors.append(f"{relative}: name must use the {namespace} namespace")
    if not 1 <= len(fields.get("description", "")) <= 1024:
        errors.append(f"{relative}: description must contain 1 to 1024 characters")
    if fields.get("license") != config["license"]:
        errors.append(f"{relative}: license must be {config['license']}")
    updated = fields.get("metadata.last-updated", "")
    if not DATE_PATTERN.fullmatch(updated):
        errors.append(f"{relative}: metadata.last-updated must be an ISO date")
    elif updated > datetime.date.today().isoformat():
        errors.append(f"{relative}: metadata.last-updated {updated} is in the future")
    body = text.split("---", 2)[2]
    if not re.search(r"(?m)^# \S", body):
        errors.append(f"{relative}: body must start with a `# Title`")
    if text.count("\n") > MAX_LINES:
        errors.append(f"{relative}: over {MAX_LINES} lines; move detail to references/")
    validate_links(path, text, errors)
    return name


def validate_personas(config: dict, errors: list[str]) -> int:
    if not config.get("persona_dir"):
        return 0
    personas = sorted((ROOT / config["persona_dir"]).glob("*.md"))
    catalog = (ROOT / "docs" / "agent-catalog.md")
    catalog_text = catalog.read_text(encoding="utf-8") if catalog.is_file() else ""
    if personas and not catalog_text:
        errors.append("docs/agent-catalog.md: missing persona catalog")
    for path in personas:
        relative = path.relative_to(ROOT)
        fields = parse_frontmatter(path.read_text(encoding="utf-8"))
        name = fields.get("name", "")
        if name != path.stem or not name.startswith(f"{config['namespace']}-"):
            errors.append(f"{relative}: persona name must match its filename and namespace")
        if not fields.get("description") or not fields.get("tools") or not fields.get("model"):
            errors.append(f"{relative}: persona needs description, tools and model")
        if name not in catalog_text:
            errors.append(f"{relative}: persona is missing from docs/agent-catalog.md")
        validate_links(path, path.read_text(encoding="utf-8"), errors)
    return len(personas)


def validate_layout(config: dict, errors: list[str]) -> None:
    """Personas and commands sit beside skills/: a skill's own agents/ holds only Codex metadata."""
    for path in sorted(SKILLS.glob("*/agents/*.md")):
        errors.append(f"{path.relative_to(ROOT).as_posix()}: personas live in {config.get('persona_dir', 'agents')}/, not inside a skill")
    for path in sorted(SKILLS.glob("*/commands")):
        errors.append(f"{path.relative_to(ROOT).as_posix()}: commands live in {config.get('command_dir', 'commands')}/, not inside a skill")


def validate_commands(config: dict, errors: list[str]) -> int:
    if not config.get("command_dir"):
        return 0
    commands = sorted((ROOT / config["command_dir"]).glob("*.md"))
    for path in commands:
        validate_links(path, path.read_text(encoding="utf-8"), errors)
    return len(commands)


def validate_readme(names: list[str], errors: list[str]) -> None:
    readme = ROOT / "README.md"
    listed = re.findall(r"(?m)^\| `([a-z0-9-]+)` \|", readme.read_text(encoding="utf-8")) if readme.is_file() else []
    for name in names:
        if listed.count(name) != 1:
            errors.append(f"README.md: list `{name}` exactly once in the skill table")
    for name in sorted(set(listed) - set(names)):
        errors.append(f"README.md: `{name}` is listed but has no skill")


def main() -> int:
    config = tomllib.loads((ROOT / "bundle.toml").read_text(encoding="utf-8"))
    errors: list[str] = []
    names = [validate_skill(path, config, errors) for path in sorted(SKILLS.glob("*/SKILL.md"))]
    deployed = sorted(SKILLS.rglob("*.md"))
    for key in ("persona_dir", "command_dir"):
        if config.get(key):
            deployed += sorted((ROOT / config[key]).glob("*.md"))
    for path in deployed:
        text = path.read_text(encoding="utf-8")
        if ".agents/" in text or "~/.agents" in text or "file://" in text:
            errors.append(f"{path.relative_to(ROOT)}: references a deployment or local-machine path")
    validate_layout(config, errors)
    persona_count = validate_personas(config, errors)
    command_count = validate_commands(config, errors)
    validate_readme([name for name in names if name], errors)
    if errors:
        print(f"{config['name']} verification failed:", *errors, sep="\n", file=sys.stderr)
        return 1
    print(f"{config['name']} verification passed ({len(names)} skills, {persona_count} personas, {command_count} commands)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

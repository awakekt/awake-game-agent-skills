# Awake Game Agent Skills

Agent skills for building games, tools and editor plugins on Awake: ECS and scenes, app
composition, Compose UI, assets, terrain, rendering diagnostics and editor plugins. Changing Awake
Core itself? Use [awake-agent-skills](https://github.com/awakekt/awake-agent-skills).

## Awake repositories

| Repository | Visibility | Holds |
|---|---|---|
| [awakekt/awake](https://github.com/awakekt/awake) | Public, Apache-2.0 | Awake Core: the engine runtime and the editor plugin contract |
| [awakekt/awake-template](https://github.com/awakekt/awake-template) | Public | The starting project for a new game |
| [awakekt/awake-plugin-template](https://github.com/awakekt/awake-plugin-template) | Public | The starting project for an editor plugin, built only on Core's plugin contract |
| [awakekt/awake-project-template](https://github.com/awakekt/awake-project-template) | Public | The app that plays an Awake Studio project; Studio's app export is built on it |
| awakekt/awake-studio | Private, AGPL-3.0 or commercial | Awake Studio: the editor app, its editor library and commercial plugins |
| [awakekt/awake-agent-skills](https://github.com/awakekt/awake-agent-skills) | Public, Apache-2.0 | Skills for maintaining Awake Core, maintainer personas, and the skill installer |
| [awakekt/awake-game-agent-skills](https://github.com/awakekt/awake-game-agent-skills) | Public, Apache-2.0 | Skills for building games, tools and editor plugins on Awake |
| awakekt/awake-studio-agent-skills | Private | Studio tier placement and creative-production personas |

Each project pins the bundles it needs in `.agents/skills.lock.toml`:

| Project | Bundles |
|---|---|
| awake | agent skills, game skills |
| awake-studio | agent skills, game skills, studio skills |

The starter templates (awake-template, awake-project-template and awake-plugin-template) ship no
agent setup: their files land in every project made from them. A game, tool or plugin project
that wants the game skills pins awake-game-agent-skills itself.

## Skills

| Skill | Use it for |
|---|---|
| `awake-app-composition` | Compose an Awake application from engine:platform, engine:bootstrap, an optional Compose UI host, and SceneSession |
| `awake-compose-authoring` | Author Compose-shaped UI on Awake's retained :awake:compose runtime |
| `awake-core-math` | Rules for using Awake's `core.math` types (Vec3, Mat4, Camera) and for writing per-frame ECS systems without allocating |
| `awake-ecs-authoring` | Rules for authoring Awake ECS components, systems and scenes - component construction, query/family costs, structural-change churn, entity lifecycle, and the scene DSL |
| `awake-ecs-scene-runtime` | Consume Awake ECS scenes from a game or sample: scene documents, entity content, scene sessions, scheduling, and lifecycle-safe activation |
| `awake-editor-plugin-authoring` | Write an editor plugin for Awake Studio or any other Awake editor host against the public Apache contract com.awakekt.awake.editor:contract |
| `awake-fbx-asset-cooking` | Convert FBX source assets, including Mixamo characters and clips, into Awake-compatible GLB assets |
| `awake-render-debug-views` | Look inside an Awake 3D frame instead of guessing |
| `awake-shadcn-recipe-consuming` | Consume Awake's in-repository shadcn design system from a sample, game, or application |
| `awake-state-management` | Manage Awake application, editor, and sample state with a thin Store/Contract, MVI, or UDF shape |
| `awake-terrain-authoring` | Author Awake heightmaps, dynamic terrain edits, geometry clipmaps, texture splatting, and terrain collision composition |
| `awake-ui-design-audit` | Audit or remediate an Awake Compose screen, screenshot, or web reference for hierarchy, content density, design-system consistency, theme handling, responsive behavior, accessibility, and visual quality |
| `awake-ui-layout-guidance` | Design and review retained Compose layouts in Awake when deciding between fixed and adaptive sizing, parent spacing, Spacer, arrangement, and alignment |
| `awake-web-to-compose` | Port a website or raw HTML/CSS into Awake Compose |

## Install in a game project

Add this bundle to the project's `.agents/skills.lock.toml`, then run the installer from
[awake-agent-skills](https://github.com/awakekt/awake-agent-skills#install-in-a-project). Pin a
release tag; the installer verifies its commit and archive digest.

```toml
version = 1

[[source]]
id = "awake-game"
kind = "maintained-core"
source = "https://github.com/awakekt/awake-game-agent-skills.git"
tag = "v0.1.0"
commit = "<commit the tag points to>"
archive_sha256 = "<sha256 of git archive --format=tar <commit>>"
license = "Apache-2.0"
skill_root = "skills"
skills_target = ".agents/skills"
skills = ["awake-ecs-authoring", "..."]
```

`bump_lock.py` from awake-agent-skills fills in `commit`, `archive_sha256` and the skill list when
it moves the pin to a newer release.

## Write a skill

Follow the [Awake skill standard](https://github.com/awakekt/awake-agent-skills/blob/main/docs/skill-authoring.md).

## Validate

    python3 scripts/verify_bundle.py

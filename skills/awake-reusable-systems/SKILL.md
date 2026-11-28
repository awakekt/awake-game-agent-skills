---
name: awake-reusable-systems
description: >
  Architecture and design rules for building reusable, game-agnostic gameplay libraries and modular
  systems on Awake: neutral mechanisms over game vocabulary, kind-plus-parameter schemas,
  data-driven formulas and typed hooks, layered dependency boundaries with thin pairwise glue
  modules, UI-free deterministic command/snapshot models, and multi-genre verification tests. Read
  before creating or extracting a shared gameplay, world, or multiplayer library on Awake.
license: Apache-2.0
metadata:
  author: awake
  last-updated: '2026-11-28'
  keywords: Awake, reusable, library, architecture, modular, DAG, deterministic, data-driven, hooks, serialization
---

# Awake Reusable Systems

Rules for designing reusable gameplay, world, and multiplayer libraries on Awake so they stay
cleanly decoupled from any single game's vocabulary, data, or UI. Pairs with
[awake-ecs-authoring](../awake-ecs-authoring/SKILL.md),
[awake-state-management](../awake-state-management/SKILL.md), and
[awake-net-authoring](../awake-net-authoring/SKILL.md).

## 1. Mechanisms, Not Game Vocabulary

A reusable library owns **mechanisms** (slots, tags, control flags, opaque kind IDs, hooks,
budgets, formulas). It never embeds a specific game's **vocabulary** (statuses, character classes,
currencies, creature types, item rarities, faction titles, or zone names).

| Don't | Do |
|---|---|
| Hard-coded boolean flags like `isStunned` or `isSilenced` | A `ControlState` (`canMove`, `canAct`, `speedScale`) derived from game-supplied effect tags through data mappings |
| Fixed enums for classes, currencies, or item rarities | Opaque string IDs (`classId`, `currencyId`, `tierId`) defined and validated in game data |
| Genre-locked structs with fields like `aggroRange` and `lootTable` on every actor | Neutral entity/rule models paired with optional, overridable named presets |

If a term only makes sense in one game or one sub-genre, move it to **data** instead of a public
Kotlin identifier.

## 2. Kind Plus Validated Parameters, Presets on Top

When a system configures varied behaviors (spawners, interest policies, movement constraints,
scoring rules), model each entry as an opaque `kind` ID plus a validated parameter bag rather than
a rigid data class whose fields only fit one genre:

```kotlin
data class ControlState(
    val canMove: Boolean = true,
    val canAct: Boolean = true,
    val speedScale: Float = 1f,
)

data class RuleSpec(
    val kind: String,
    val parameters: Map<String, String> = emptyMap(),
) {
    fun validate(schema: Map<String, (String) -> Boolean>) {
        require(kind.isNotBlank()) { "kind must not be blank" }
        for ((key, check) in schema) {
            val value = parameters[key]
            require(value != null && check(value)) { "invalid parameter '$key': $value" }
        }
    }
}
```

- Ship ready-made defaults as **presets**: named, data-driven bundles that a game can adopt,
  override, or ignore completely. A preset is a convenience, never the only configuration path.
- Keep every configuration model serializable, versioned, and validated with actionable error
  messages (using `:awake:core:schema` where schema validation applies).

## 3. Data-Driven Numbers, Formulas, and Typed Hooks

- **No tunable gameplay constants in code.** Drop rates, cooldowns, ranges, scaling curves, caps,
  and hysteresis margins belong in configuration data with documented, overridable defaults.
- **Support both Kotlin and data expressions for formulas.** Accept a narrow Kotlin functional
  interface for code-first games alongside a data expression path backed by
  `:awake:core:expression` so designers can tune calculations without recompiling.
- **Model game-specific rules as typed extension hooks.** Conditions ("may this item occupy this
  slot?", "should this entity stay pinned above a visibility cap?") and side-effect callbacks
  belong behind typed hook interfaces with generic built-ins rather than `if`/`when` branches on
  game concepts.

```kotlin
fun interface RuleHook<C, R> {
    fun evaluate(context: C): R
}
```

## 4. Layered Dependency DAG and Pairwise Glue Modules

Keep modules independently adoptable with strict one-way Gradle dependency boundaries:

```text
Awake Core (:awake:ecs, :awake:core:math, :awake:core:expression, :awake:ai, :awake:net:api)
        ↑
Runtime utilities        (persistence adapters, integrity, diagnostics)
        ↑                           ↑
World systems            Multiplayer systems
(spatial streaming,      (interest grids, crowd pacing,
 crowd/effect budgets)    replication, server hosting)
        ↑                           ↑
Genre gameplay modules   (combat, abilities, items, quests, dialogue, hud-state, ...)
```

- **Keep horizontal peers decoupled.** World systems must not depend on multiplayer (singleplayer
  open-world games stay networking-free), and multiplayer must not depend on world streaming or
  genre rules (co-op and arena games stay lightweight).
- **Never couple two standalone gameplay modules directly.** If module A (`combat`) and module B
  (`abilities`) are useful independently, keep zero dependency between them. When a game uses both
  and needs standard integration, ship a thin pairwise glue module (`combat-abilities`) whose only
  job is wiring A's interface to B's model.
- **Enforce layer boundaries in Gradle.** Fail the build automatically when a lower layer imports
  an upper layer or when a standalone module introduces an unintended sibling dependency.

## 5. Deterministic, Command-Based, UI-Free, and Snapshot-able

Pure rule and state libraries must not own rendering, UI widgets, ECS entity creation, or network
sockets:

- **Deterministic inputs:** Express simulation updates as deterministic functions of current state,
  explicit command inputs, and an explicit random seed so servers stay authoritative and clients
  can predict identically.
- **Command-and-refusal contracts:** Accept mutations as typed commands that return an explicit
  outcome or refusal reason instead of silently mutating or throwing on gameplay rejections.
- **Snapshot and restore:** Support serializable state snapshots so games can save, transfer across
  zones/channels, and roll back cleanly.
- **UI-free state libraries:** Keep HUD, overlay, and settings libraries strictly to plain state
  and rules (action slots, unit frame data, hit numbers, visibility caps). Let the consuming game
  own all Compose or Canvas layout, widgets, and visual themes (**one owner per capability**).

```kotlin
sealed interface CommandResult<out E> {
    data class Applied<E>(val events: List<E>) : CommandResult<E>
    data class Refused(val reasonCode: String) : CommandResult<Nothing>
}
```

## 6. Stable Core Dependencies and Proof of Genericity

- **Build on stable Core APIs.** Depend on stable foundations (`:awake:ecs`, `:awake:core:math`,
  `:awake:core:expression`, `:awake:core:schema`, `:awake:ai`, `:awake:net:api`) rather than
  coupling large libraries to moving rendering or UI internals. If a missing primitive belongs in
  the engine itself, add it to Core instead of re-implementing a private copy.
- **Keep pixel tests where pixels are drawn.** Reusable logic libraries verify state transitions,
  determinism, serialization round-trips, and allocation budgets — never Core rendering baselines.
- **Prove genericity in every module's test suite:**
  1. **Two distinct synthetic themes** configuring the same library with completely different
     vocabulary, rules, and numbers.
  2. **One off-genre test** proving the mechanism works outside its primary stereotype (for
     example, a farming or wave-defense scenario reusing an item or spawn library).
  3. **One pure data-only test** configuring the module solely from serialized data and expressions
     with zero custom Kotlin hooks.
  4. **Zero real-game leakage:** Never include any real game's names, formulas, assets, or
     game-authored data in library code, comments, presets, or test fixtures.

## Review Checklist

- [ ] Public identifiers name mechanisms, never a specific game's vocabulary.
- [ ] Configurable behaviors use `kind` + validated parameter bags with optional presets.
- [ ] Tunable numbers live in data; dynamic formulas support both Kotlin and `:awake:core:expression`.
- [ ] Game-specific decisions use typed hooks instead of hard-coded branches.
- [ ] Layer DAG is strictly one-way; sibling standalone modules connect only via thin glue modules.
- [ ] Logic is deterministic, command-based, UI-free, and snapshot/restore-capable.
- [ ] Tests cover two synthetic themes, one off-genre scenario, and one data-only configuration.
- [ ] No real game's names, content, or authored logic appear anywhere in the module.

## Route Elsewhere

- ECS components, systems, and allocation discipline: [awake-ecs-authoring](../awake-ecs-authoring/SKILL.md).
- App and HUD state boundaries (Store/MVI/UDF): [awake-state-management](../awake-state-management/SKILL.md).
- Binary protocols and Ktor game server setup: [awake-net-authoring](../awake-net-authoring/SKILL.md).
- Wiring an app root and `SceneSession` lifecycle: [awake-app-composition](../awake-app-composition/SKILL.md).
- In-game Canvas vs. Compose UI binding: [awake-canvas-binding](../awake-canvas-binding/SKILL.md).
- Editor-contract plugins: [awake-editor-plugin-authoring](../awake-editor-plugin-authoring/SKILL.md).

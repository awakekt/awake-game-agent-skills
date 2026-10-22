---
name: awake-ecs-authoring
description: >
  Rules for authoring Awake ECS components, systems, gameplay cues, and scenes - component
  decomposition, EcsTag state markers, AnimationCue/SoundCue pipelines, query/family costs,
  structural-change churn, entity lifecycle, and the scene DSL. Read before adding a component,
  writing a System, triggering animation/sound, or building entities with the scene { } DSL.
  Trigger keywords - ECS, World, entity, component, System.update, queryEach, family, Poolable,
  EcsTag, AnimationCue, SoundCue, AudioSystem, scene DSL, EntityScope, cameraEntity, MeshRenderer,
  Transform, spawn, destroy.
license: Apache-2.0
metadata:
  author: awake
  last-updated: '2026-09-17'
---

# Authoring ECS components, systems and scenes in Awake

Pairs with `awake-core-math` (vector/matrix and per-frame allocation rules) and
`awake-state-management` (in-game HUD and editor Store/Contract separation).

## Components

A component is plain data with a single responsibility. Behaviour lives in a `System`.

```kotlin
class MovementControl : Poolable {
    var moveX: Float = 0f
    var moveZ: Float = 0f

    // reset() must clear EVERY field. A pooled instance is reused; anything you forget
    // leaks into the next entity that gets this instance.
    override fun reset() {
        moveX = 0f
        moveZ = 0f
    }
}
```

Two rules that have already bitten this codebase:

- **`reset()` must clear every field, including flags.** `CameraComponent.needsReset` was
  omitted, so a recycled component came back still flagged and re-ran its mode reset on the
  next entity's first frame.
- **Do not rely on reflective construction.** `world.add<T>(entity)` resolves a no-arg
  constructor at runtime. Kotlin does not emit one for a component holding a value class
  (`Transform.parent: Entity?` is the live example - `Entity` is a value class), and iOS and
  wasmJs do not support it at all. Always pass an explicit factory or instance:

```kotlin
world.add(entity, Name(name))              // explicit instance
world.ensure(entity, ::MovementControl)    // explicit factory
Modifier().configure(::Transform) { ... }  // DSL takes a factory for the same reason
```

**Payload-free tags use `EcsTag`.** A component whose presence is its entire value should be a
singleton object implementing `EcsTag`. The store and maintained `Family1`/`Family2` caches keep
entity IDs plus one canonical singleton instead of one repeated reference per entity:

```kotlin
data object IsSelected : EcsTag
world.add(entity, IsSelected)
```

Keep game-specific tag vocabulary in the game repository. Awake owns only the generic contract
and storage. Never implement `EcsTag` with a class that creates multiple instances; the store
rejects it because a tag has exactly one canonical value.

**Iterate tag families; do not request arrays on hot paths.** `family.forEach`,
`forEachComponent`, and `forEachComponents` branch on representation once before the dense loop.
Calling `components()`, `componentsA()`, or `componentsB()` for an `EcsTag` lazily materializes
repeated singleton references for source compatibility. `componentAt` does not materialize one.

### Editor Capability Components vs Persistent Components vs UI State

The ECS `World` is the **Single Source of Truth** for both runtime simulation and editor authoring.

1. **Persistent Scene Components** (`TerrainComponent`, `TerrainAssetReference`):
   - Represent the persistent scene entity saved to scene documents (`.scene.json`) or asset manifests (`.terrain.json`).
   - Must carry all asset provenance references (`assetPath`, `splatMapPath`, `colorMapPath`, `heightmapAssetPath`, `layers`).
2. **Ephemeral Tool Capability Components** (`TerrainBrushComponent`, `CameraGizmoComponent`, `Selectable`):
   - Attached to the entity in `World` only while actively authoring.
   - Hold interactive tool state: brush radius, strength, falloff, sculpt tool, brush shape, target height, active layer, viewport shading mode (`Textured`, `SplatRgba`, `Satellite`).
   - Systems and editor tools (a `TerrainMeshRuntimeSystem`, a plugin `ViewportToolProvider` brush) read directly from these components each frame.
3. **Stateless UI Panels**:
   - Compose UI panels and inspector state holders (`*InspectorState`) are pure observers and controllers.
   - **Never store canonical domain or tool state in UI-only memory.** UI state must synchronize with the entity's ECS components in the `World` immediately on interaction.

## Gameplay state, animation, and audio cues

Read [gameplay-cues-and-state.md](references/gameplay-cues-and-state.md) before writing gameplay
components, combat/skill state transitions, animation systems, or audio triggers.

1. **No God-Components or God-Systems**:
   - Never pack stats, health, cooldowns, bitflags, hit lists, boolean animation flags, and UI
     request queues into one `Combatant` or `PlayerState` class. Split into orthogonal data
     components (`Health`, `CombatStats`, `CombatTarget`) and `EcsTag` state markers (`Dead`,
     `Stunned`, `InCombat`) so `family`/`queryEach` filters at the storage level instead of running
     deep `if/else` chains.
   - Never keep 10+ `HashMap<Entity, ...>` side tables inside a single 700-line `System` (such as a
     monolithic `NetClientSystem`). Store per-entity state on an ECS component and split independent
     responsibilities into separate systems.
2. **Trigger animations and audio via typed one-shot Cues (`AnimationCue`, `SoundCue`)**:
   - Never poll and clear boolean flags (`attackAnimationPending = false`) on domain components.
   - Never diff domain state (`count > prevInventoryCount || currency > prevCurrency` or
     `attackSequences: HashMap<Entity, Long>`) inside `GameAudioSystem` to guess what happened.
   - Emit sealed `AnimationCue` and `SoundCue` events at the authoritative transition site (loot
     collected, strike landed, skill cast) and drain them once per frame in presentation systems.
3. **Declarative Animation Priority Table, never component stashing**:
   - Never rip `LocomotionAnimation` off an entity and stash it in a system's
     `HashMap<Entity, LocomotionAnimation?>` when an entity dies.
   - Resolve clips in a single `AnimationCueSystem` using a priority table (`DEATH > SKILL_CAST >
     ATTACK > HIT_REACT > LOCOMOTION`) instead of scattered string-prefix `if/else` checks.
4. **Use `:awake:scene:audio` (`AudioSystem`, `AudioSource`, `AudioListener`)**:
   - Use Awake's built-in `AudioSystem` for 3D spatial attenuation and stereo panning, paired with a
     lightweight `SoundCueSystem` for one-shot gameplay SFX.

## Systems

```kotlin
class SpinSystem : System {
    override fun update(world: World, delta: Float) {
        world.queryEach(Transform::class, SpinControl::class) { _, transform, spin ->
            transform.rotation.y = spin.radians
        }
    }
}
```

**Query cost.** The 1- and 2-component typed `queryEach` overloads run off maintained family
caches and allocate nothing. The `vararg` overload calls `types.toSet()` on every invocation -
avoid it in a per-frame path.

**Family storage changes require matched evidence.** Use the exact pre-change commit, Kotlin
toolchain, JDK, entity counts, forks, warmups, and measurements. Publish score and error for tag
and ordinary-component controls; capture GC evidence; run every KMP ECS test target. Cross-runtime
Flecs/EnTT/Bevy/Unity numbers are architecture references, never substitutes for Awake's same-JVM
Fleks/Artemis/Ashley harness. See `docs/tasks/archive/2026-08-21-ecs-family-tag-columns.md`.

**Archetype promotion currently fails its gate.** The benchmark-only pure-archetype control
performs real stable-row migration and covers 256 tag signatures. Production maintained families
still win stable and required/excluded query iteration, while sparse dynamic tags avoid the
archetype control's roughly 7.6x churn penalty at 100k. Do not add archetype routing from table
locality intuition alone; first demonstrate a new real workload that clears the matched gate in
`docs/tasks/archive/2026-08-18-ecs-hybrid-archetype-sparse-set.md`.

**Structural changes are not free.** `world.add` / `world.remove` invalidate the query cache
and churn the family caches. Never add-and-remove the same component every frame:

When a hot structural path already owns a `ComponentTypeId`, keep class resolution outside the
entity loop. The cached-ID overloads exist to avoid repeated `T::class`/KClass work; do not route
them back through class-based mutation helpers. See
`docs/tasks/archive/2026-08-21-ecs-cached-type-id-churn.md`.

```kotlin
// Before: two full query-cache invalidations per frame, plus a fresh allocation, purely to
// zero two floats that the next system overwrites anyway.
world.remove<MovementControl>(target)
world.ensure(target, ::MovementControl)

// After: keep the component resident, mutate its fields.
world.get<MovementControl>(target)?.apply { moveX = 0f; moveZ = 0f }
```

**Never mutate the world while iterating it.** `queryEach` walks a family cache whose backing
array is swap-mutated by removal. Collect first, then act:

```kotlin
val previouslyActive = world.query(ActiveCamera::class)
previouslyActive.forEach { world.remove<ActiveCamera>(it) }
```

**Registration order is behaviour.** Systems run in registration order within a phase. Input
must precede intent consumers; the camera pose must be settled before anything reads its basis;
gameplay systems that emit `AnimationCue` / `SoundCue` must precede the cue drain systems.
If a system reads another's output, say so in a comment at the registration site.

## Scenes and entities

```kotlin
world.scene {
    val cube = entity("SpinningCube") {
        transform(y = 0.5f)
        with(SpinControl())
    }
    entity("MainCamera") {
        camera(CameraMode.ThirdPerson, target = cube)
    }
}
```

- `entity("name") { }` provides an `EntityScope` receiver where components are attached directly to the entity.
- `with(component)` attaches a pre-existing component instance directly to the entity.
- `configure(::Type) { }` takes an explicit constructor factory (see the reflective-construction rule above).
- Child entities are spawned via nested `entity("child") { }` blocks and automatically parented to the enclosing entity's `Transform`.

**A camera needs both halves.** `Camera` is the lens `RenderSystem` renders from;
`CameraComponent` is the control state `CameraSystem` drives. An entity carrying only one is
silently inert - it will never be rendered from, or never move. Calling `camera(...)` inside `entity { }`
attaches both; prefer it over hand-assembling either.

Attaching a raw `core.math.Camera` does **not** make an entity a camera - it registers under
its own type and matches no scene query. Wrap it: `entity("camera") { camera(lens = myCoreCamera) }`.

**Own what you destroy.** Keep the `Entity` handles you spawned and destroy exactly those.
A global `queryEach(SpinControl::class) { destroy(it) }` in a teardown will take out every
other system's entities too.

**Free GPU resources.** Meshes and materials created in `onActivate`/`ensureSpawned` are not
owned by the ECS. Destroy them in `onDeactivate`, or every activate/deactivate cycle leaks one
mesh and one material.

## DSL builders

`@DslMarker` is load-bearing. `SceneGameDsl` is annotated `@AwakeSceneDsl` so the enclosing
`GameSpecDsl` receiver is hidden inside its block. Without it, an inner `scene(name) { }` call
silently resolved to the *outer* `GameSpecDsl.scene` extension and installed a second scene
module - two `World`s, two render callbacks, and `requireService<SceneGameRuntime>()` returning
the wrong one. Annotate every nested builder receiver.

When you add or change a builder overload, check that a call inside a nested block still binds
to the member you expect. An overload that merely *fails to match* does not error - it falls
through to whatever outer extension does match.

## Checklist

- [ ] `reset()` clears every field of the component, flags included.
- [ ] Components are single-purpose data; discrete states use `EcsTag` singletons instead of god-component `if/else` trees.
- [ ] Animations and sounds are triggered by typed one-shot cues (`AnimationCue`, `SoundCue`), never by boolean flag polling or diffing domain counts in `HashMap`s.
- [ ] Animation playback uses a priority table in one system; removed components (`LocomotionAnimation`) are never stashed in a system `HashMap`.
- [ ] Spatial audio uses `:awake:scene:audio` (`AudioSystem`, `AudioSource`, `AudioListener`).
- [ ] Hot tag-family code uses iteration or `componentAt`, not a materialized `components*()` array.
- [ ] No reflective `world.add<T>(entity)` - factory or instance passed explicitly.
- [ ] No per-frame add/remove of the same component, and no structural mutation during `queryEach`.
- [ ] Camera entities carry both `Camera` and `CameraComponent`.
- [ ] Teardown destroys only entities this feature spawned, plus its GPU resources.
- [ ] Editor tool parameters and asset references live in ECS components on the entity, never in UI-only memory.
- [ ] New nested DSL receivers are `@DslMarker`-annotated.

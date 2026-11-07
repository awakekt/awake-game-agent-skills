---
name: awake-ecs-authoring
description: >
  Rules for authoring Awake ECS components, systems, gameplay cues, and scenes - component
  decomposition, EcsTag state markers, typed animation and audio cues, query/family costs,
  structural-change churn, entity lifecycle, and the scene DSL. Read before adding a component,
  writing a System, triggering animation/sound, or building entities with the scene { } DSL.
  Trigger keywords - ECS, World, entity, component, System.update, queryEach, family, Poolable,
  EcsTag, AudioCueQueue, emitAudioCue, AudioSystem, scene DSL, EntityScope, cameraEntity, MeshRenderer,
  Transform, spawn, destroy.
license: Apache-2.0
metadata:
  author: awake
  last-updated: '2026-11-07'
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

Two rules:

- **`reset()` must clear every field, including flags.** Leave out a flag such as
  `CameraRig.needsReset` and a recycled component comes back still flagged. It then reruns its
  mode reset on the next entity's first frame.
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

1. **Persistent Scene Components** (`TerrainComponent`, `TerrainSurfaceReference`):
   - Saved to the scene document (`.scene.json`) through their scene binding, such as `SceneTerrain`.
   - Carry everything needed to rebuild the entity: data, asset paths and surface references.
2. **Ephemeral Tool Capability Components** (your tool's own components, such as a terrain brush):
   - Attached to the entity in `World` only while actively authoring.
   - Hold interactive tool state: brush radius, strength, falloff, brush shape, target height, active layer.
   - Systems and editor tools (a plugin `ViewportToolProvider` brush) read them directly each frame.
3. **Stateless UI Panels**:
   - Compose UI panels and inspector state holders (`*InspectorState`) are pure observers and controllers.
   - **Never store canonical domain or tool state in UI-only memory.** UI state must synchronize with the entity's ECS components in the `World` immediately on interaction.

## Gameplay state, animation, and audio cues

Read [gameplay-cues-and-state.md](references/gameplay-cues-and-state.md) before writing gameplay
components, combat/skill state transitions, animation systems, or audio triggers.

1. **No God-Components or God-Systems**:
   - Never pack stats, health, cooldowns, bitflags, hit lists, boolean animation flags, and UI
     request queues into one combatant or player-state class. Split it into small data components
     and `EcsTag` state markers (dead, stunned, in combat) so `family`/`queryEach` filters at the
     storage level instead of running deep `if/else` chains. The reference shows the split.
   - Never keep 10+ `HashMap<Entity, ...>` side tables inside a single 700-line `System`, such as
     one network client system. Store per-entity state on an ECS component and split independent
     responsibilities into separate systems.
2. **Trigger animations and audio via typed one-shot cues**:
   - Never poll and clear boolean flags (`attackAnimationPending = false`) on domain components.
   - Never diff domain state (`count > prevInventoryCount || currency > prevCurrency` or
     `attackSequences: HashMap<Entity, Long>`) inside an audio system to guess what happened.
   - Emit a cue at the authoritative transition site (loot collected, strike landed, skill cast)
     and drain it once per frame. Core has no animation cue type: declare your game's own sealed
     cue type. For sound, call `World.emitAudioCue`, which queues a `OneShotAudioCue` on the
     entity's `AudioCueQueue`.
3. **Declarative Animation Priority Table, never component stashing**:
   - Never rip `LocomotionAnimation` off an entity and stash it in a system's
     `HashMap<Entity, LocomotionAnimation?>` when an entity dies.
   - Resolve clips in one system with a priority table (`DEATH > SKILL_CAST > ATTACK >
     HIT_REACT > LOCOMOTION`) instead of scattered string-prefix `if/else` checks.
4. **Use `:awake:scene:audio` (`AudioSystem`, `AudioSource`, `AudioListener`, `AudioCueQueue`)**:
   - Awake's `AudioSystem` does 3D spatial attenuation and stereo panning. It also drains every
     `AudioCueQueue` each frame, so one-shot gameplay SFX need no audio system of your own.

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
Fleks/Artemis/Ashley harness. See "Family tag-column specialization" in `docs/ecs-benchmark-scorecard.md`.

**Archetype promotion currently fails its gate.** The benchmark-only pure-archetype control
performs real stable-row migration and covers 256 tag signatures. Production maintained families
still win stable and required/excluded query iteration, while sparse dynamic tags avoid the
archetype control's roughly 7.6x churn penalty at 100k. Do not add archetype routing from table
locality intuition alone; first demonstrate a new real workload that clears the matched gate in
"Sparse vs hybrid vs pure archetype decision" in `docs/ecs-benchmark-scorecard.md`.

**Structural changes are not free.** `world.add` / `world.remove` invalidate the query cache
and churn the family caches. Never add-and-remove the same component every frame:

When a hot structural path already owns a `ComponentTypeId`, keep class resolution outside the
entity loop. The cached-ID overloads exist to avoid repeated `T::class`/KClass work; do not route
them back through class-based mutation helpers. See "Cached type-ID structural churn" in
`docs/ecs-benchmark-scorecard.md`.

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
gameplay systems that emit cues must precede the systems that drain them, such as `AudioSystem`.
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

**A camera needs both halves.** `Camera` is the lens `RenderSystem3D` renders from;
`CameraRig` is the control state `CameraSystem` drives. An entity carrying only one is
silently inert - it will never be rendered from, or never move. Calling `camera(...)` inside `entity { }`
attaches both; prefer it over hand-assembling either.

Attaching a raw `core.math.Lens` does **not** make an entity a camera - it registers under
its own type and matches no scene query. Wrap it: `entity("camera") { camera(lens = myLens) }`.

**Own what you destroy.** Keep the `Entity` handles you spawned and destroy exactly those.
A global `queryEach(SpinControl::class) { destroy(it) }` in a teardown will take out every
other system's entities too.

**Free GPU resources.** Meshes and materials created in `onActivate`/`ensureSpawned` are not
owned by the ECS. Destroy them in `onDeactivate`, or every activate/deactivate cycle leaks one
mesh and one material.

## DSL builders

`@DslMarker` is load-bearing. `SceneAppDsl` is annotated `@AwakeSceneDsl` so the enclosing
`AppSpecDsl` receiver is hidden inside its block. Without it, an inner `scene(name) { }` call
silently resolves to the *outer* `AppSpecDsl.scene` extension and installs a second scene
module - two `World`s, two render callbacks, and `requireService<SceneAppLifecycleRuntime>()`
returning the wrong one. Annotate every nested builder receiver.

When you add or change a builder overload, check that a call inside a nested block still binds
to the member you expect. An overload that merely *fails to match* does not error - it falls
through to whatever outer extension does match.

## Checklist

- [ ] `reset()` clears every field of the component, flags included.
- [ ] Components are single-purpose data; discrete states use `EcsTag` singletons instead of god-component `if/else` trees.
- [ ] Animations and sounds are triggered by typed one-shot cues (your own animation cue type, `AudioCueQueue` for sound), never by boolean flag polling or diffing domain counts in `HashMap`s.
- [ ] Animation playback uses a priority table in one system; removed components (`LocomotionAnimation`) are never stashed in a system `HashMap`.
- [ ] Spatial audio uses `:awake:scene:audio` (`AudioSystem`, `AudioSource`, `AudioListener`).
- [ ] Hot tag-family code uses iteration or `componentAt`, not a materialized `components*()` array.
- [ ] No reflective `world.add<T>(entity)` - factory or instance passed explicitly.
- [ ] No per-frame add/remove of the same component, and no structural mutation during `queryEach`.
- [ ] Camera entities carry both `Camera` and `CameraRig`.
- [ ] Teardown destroys only entities this feature spawned, plus its GPU resources.
- [ ] Editor tool parameters and asset references live in ECS components on the entity, never in UI-only memory.
- [ ] New nested DSL receivers are `@DslMarker`-annotated.

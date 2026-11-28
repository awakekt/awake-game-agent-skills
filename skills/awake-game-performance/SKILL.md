---
name: awake-game-performance
description: >
  Performance engineering patterns for games built on Awake across Desktop, Web (WasmJs), and
  4 GB mobile targets: zero-allocation ECS systems, linear O(N) hierarchy scans, loading-screen
  and Frame-1 anti-stall architecture, budgeted collider/cell streaming, unidirectional performance
  settings, and network burst resilience. Read before optimizing frame pacing, loading screens,
  open-world streaming, dense entity scenes, or mobile memory budgets.
license: Apache-2.0
metadata:
  author: awake
  last-updated: '2026-11-28'
  keywords: Awake, performance, zero-allocation, ECS, loading, streaming, StaticColliderStreamSystem, mobile, WasmJs, frame-pacing, netcode
---

# Awake Game Performance

Architectural performance rules for shipping smooth 30-60 FPS cross-platform games on Awake
(4 GB Android phones through Desktop and WasmJs). Pairs with
[awake-ecs-authoring](../awake-ecs-authoring/SKILL.md),
[awake-core-math](../awake-core-math/SKILL.md), and
[awake-ecs-scene-runtime](../awake-ecs-scene-runtime/SKILL.md).

## 1. Zero-Allocation ECS & Linear Scans

Per-frame GC churn and quadratic entity queries are the #1 cause of frame-time spikes once entity
counts climb.

- **Hoist `KClass` tokens into `private companion object` constants.** Passing `Transform::class`
  inline inside `System.update` repeatedly allocates class references on hot paths.
- **Never nest `world.queryEach` loops ($O(N^2)$).** When matching child entities (meshes, sockets,
  attachments) to parent entities, run one linear $O(N)$ pass that groups children into a reusable
  `HashMap` of pooled `EntityList` buffers, process only dirty parents, then clear the lists without
  releasing their backing arrays.
- **Reuse scratch buffers across frames.** Keep primitive arrays, `EntityList`, and `EntitySet`
  instances as fields on the `System` (or per-worker scratch for parallel jobs) and grow them by
  doubling on demand instead of allocating `List`, `Map`, or `sortedBy` copies every frame.
- **Skip steady-state work with dirty flags and `Family`.** Maintain a `Family` cache or version
  counter on state components so idle entities cost $O(1)$ per tick instead of re-evaluating
  unchanged hierarchy state.

```kotlin
class HierarchySyncSystem : System {
    private val childrenByParent = HashMap<Entity, EntityList>()
    private val usedParents = EntityList()

    override fun update(world: World, delta: Float) {
        usedParents.clear()
        world.queryEach(CHILD, TRANSFORM) { child, _, transform ->
            val parent = transform.parent ?: return@queryEach
            val bucket = childrenByParent.getOrPut(parent) { EntityList() }
            if (bucket.isEmpty) usedParents.add(parent)
            bucket.add(child)
        }
        usedParents.forEach { parent ->
            val bucket = childrenByParent.getValue(parent)
            // Process dirty parent using bucket, then clear for reuse next frame.
            bucket.clear()
        }
    }

    private companion object {
        val CHILD = ChildMarker::class
        val TRANSFORM = Transform::class
    }
}
```

## 2. Loading Screens & Frame-1 Anti-Stall Rules

Moving file reads to background dispatchers is not enough if decode bursts starve the render loop
or dump thousands of physics bodies onto Frame 1.

- **Guard cooperative `yield()` strictly to single-threaded hosts (WasmJs).** Yielding between heavy
  decode chunks keeps WasmJs loading animations responsive, but unconditional `yield()` on JVM or
  Android background threads suspends large local frames and can retain scene graphs across GC
  checks:
  ```kotlin
  internal suspend fun yieldLoadingFrame() {
      if (ioDispatcher === Dispatchers.Default) yield()
  }
  ```
- **Short-circuit world-projected HUD while an opaque loading cover is active.** Skip nameplate
  projection, floating combat text, and world-anchored canvas layout while a loading overlay covers
  the viewport.
- **Budget Frame-1 static physics colliders.** Large scenes with hundreds or thousands of static
  `PhysicsBody` or terrain colliders should never initialize synchronously on Frame 1. Opt into
  `StaticColliderStreamSystem` (`:awake:project:runtime`) or stream static colliders in two rings:
  1. Immediately activate colliders inside a safe landing radius around spawn/teleport so characters
     cannot fall through floors.
  2. Activate outer colliders and park distant bodies over subsequent fixed ticks with a fixed
     per-step budget, exempting characters, NPCs, triggers, and dynamic bodies.
- **Strip unused controllers before physics initialization.** If server-driven or non-player entities
  carry authored character-controller components that the client does not simulate locally, strip
  them in a fixed-phase system *before* the character-controller system builds native controllers.
- **Never block the UI or render thread on media/audio setup.** On Android, prepare streaming music
  or splash video asynchronously rather than calling synchronous `prepare()` on the main thread.

## 3. Open-World Streaming & Mobile Memory Discipline

Treat 4 GB mobile devices as the baseline memory ceiling.

- **Always separate enter and exit radii (hysteresis).** Terrain tiles, prop cells, streamed models,
  and distance-culled visuals need wider leave distances than enter distances so walking along a
  cell seam never thrashes loads and unloads every few frames.
- **Budget activations and parks per frame.** Cap how many cells, models, or colliders attach or
  tear down in a single tick so crossing a region boundary spreads work smoothly over multiple
  frames instead of spiking frame time.
- **Release scene caches explicitly on close and zone switch.** Clear pooled maps, entity sets, and
  retained asset caches in `AutoCloseable.close()` when leaving a `SceneSession` so closed scenes
  reclaim cleanly under GC.

## 4. State, Settings & Culling Boundaries

- **Keep performance settings out of global Compose state.** Store process-wide performance choices
  as plain thread-safe state (`@Volatile`) and snapshot them into the screen's unidirectional view
  state on update rather than exposing global `mutableStateOf` or `StateFlow` singletons.
- **Decouple independent overrides from `Auto` presets.** Let players adjust individual safety
  controls (detail protection, entity limits, UI skip) without forcing the overall graphics preset
  off `Auto` and disabling automatic device-tier adaptation.
- **Exempt non-networked actors and headless worlds from visual culling.** When capping dense
  entity rendering or effects by distance, require an active `Camera` (`eye != null`) and gate
  culling to the networked/crowd marker component so preview mannequins, UI dolls, and headless
  screenshot/benchmark tests are never unexpectedly hidden.
- **Apply priority pinning and hysteresis before culling.** Always keep gameplay-critical entities
  (local player, active target, combat opponents, party/allies) visible regardless of count caps,
  and add a small distance hysteresis bonus to already-visible bystanders to prevent boundary pop.

## 5. Network Burst Resilience

- **Size reliable client inboxes for scene-entry bursts.** A client entering a busy hub while loading
  can buffer thousands of reliable messages before the first world tick drains them.
- **Fail closed on reliable inbox overflow.** Never silently drop reliable state messages when a
  channel fills up — silent drops corrupt entity state (missing gear, ghost actors, desynced stats).
  Instead, close the `Transport` cleanly so reconnection rebuilds authoritative state.
- **Pace high-fanout spawns on the server.** When many actors enter view on the same tick, bound
  how many fresh bystander spawns emit per snapshot (nearest-first, while keeping pinned combat or
  ally entities immediate) using per-worker reusable scratch buffers.

## 6. Verification Checklist

Before declaring a performance or streaming change done, verify with automated tests:

1. **Zero-allocation probe:** Assert hot-path `System.update` loops stay within allocation budget
   across steady-state frames.
2. **Teleport & streaming test:** Verify landing-radius colliders activate on tick 1, outer
   colliders drain smoothly across subsequent ticks without extra movement, and exemptions hold.
3. **Dense-scene / burst test:** Populate a scene well above target caps and verify linear setup,
   priority pinning, hysteresis stability, and headless restoration when no `Camera` is present.
4. **Reliable inbox overflow test:** Verify burst headroom delivers cleanly with zero drops and
   overflow closes the link rather than dropping state silently.
5. **Teardown memory check:** Verify closing the scene or `SceneSession` releases cached references.

## Route Elsewhere

- Component pools, `EcsTag`, and `Family` query details: [awake-ecs-authoring](../awake-ecs-authoring/SKILL.md).
- Vector/matrix math and zero-alloc `Vec3`/`Mat4` rules: [awake-core-math](../awake-core-math/SKILL.md).
- Scene sessions, scheduling, and missing-content resilience: [awake-ecs-scene-runtime](../awake-ecs-scene-runtime/SKILL.md).
- Unidirectional Store/MVI boundaries for HUD and menus: [awake-state-management](../awake-state-management/SKILL.md).
- Binary packet codecs and Ktor server authoring: [awake-net-authoring](../awake-net-authoring/SKILL.md).
- Heightmaps, clipmaps, and terrain streaming: [awake-terrain-authoring](../awake-terrain-authoring/SKILL.md).

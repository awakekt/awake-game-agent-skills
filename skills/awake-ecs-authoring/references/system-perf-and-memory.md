# Game System Performance, Memory Lifecycle, and Mobile Tier Ceilings

Extends `SKILL.md`. Read before writing a gameplay, streaming, or world-anchored HUD `System`
whose `update()` runs every frame.

## 1. Key system side-tables by `Entity`, never by component instances

Never store an ECS component object — whether a mutable `data class` or a regular class like
`ParticleEmitter` — as a key in a `Map` or `Set`:

- Mutable `data class` keys (`Transform`, `TerrainComponent`, etc.) change `hashCode()` when a
  `var` field mutates, stranding entries and leaking duplicates.
- Non-`data` component objects (`ParticleEmitter`, `MeshRenderer`) pin the dead component and its
  internal buffers in heap after `world.destroy(entity)` until the map is cleared.

Key per-entity side-tables by `Entity` and prune dead entries (`!world.isAlive(entity) ||
!world.has(entity, COMPONENT)`) on every active tick — not only when a system goes idle.

Every `AutoCloseable` system that caches prefabs, parsed nodes, spawned models, or channels must
clear **all** caches and close channels inside `close()` so scene transitions do not leak them.

## 2. Choosing the right query/system pattern, `FamilySpec`, `runTick`, and unboxed bags

| Need | Use | Why |
|---|---|---|
| 1–2 packed components, no extra filter | `world.queryEach<A, B> { ... }` or `Family1System` / `Family2System` | Zero `World.get` lookups, zero allocations |
| 1–2 packed components + `all` / `one` / `exclude` | Hoisted `FamilySpec` (`FamilySpec.exclude(...)`, `FamilySpec.all(...)`, `familySpec { ... }`) with `world.family(TYPE_A, TYPE_B, SPEC)` or `Family1System` / `Family2System` | **3.3–3.6× faster** than unpacked `world.family { ... }` + `World.get`; array-indexed zero-alloc lookup |
| Whole-tick early-out (`delta <= 0f`, paused, table/terrain not loaded) | Override `shouldProcess(world, delta): Boolean` | Skips `begin`/`process`/`end` in O(1) |
| Hot `Family1System`/`Family2System`/`IteratingSystem` when 3+ subclasses exist | `override fun update(world: World, delta: Float) = runTick(world, delta) { ... }` | Keeps `process` **monomorphic** on JVM and avoids Wasm `call_ref` (**2.2–3.3× faster** at 10k entities than megamorphic `super.update`) |
| 3+ components or arbitrary predicate | `IteratingSystem(spec)` or `world.family(spec)` + hoisted `ComponentType<T>` handles | Avoids per-entity `KClass` lookups |
| HUD windows, Compose UI sync, and Store effect draining | `SceneBridge` (`SceneAppDsl.bridge { ... }`) + `ContextualEffectDrainer<C>` (never an ECS `System`) | Keeps Compose out of ECS, resolves `localPlayer` once per frame instead of N times, gives 0-frame click latency (`beforeAdvance` drain / `afterAdvance` sync), and closes all owned stores automatically |

- Lead `queryEach` with the narrowest component (a player/active marker before `MovementControl`;
  `MeshRenderer` / `ParticleEmitter` / `ParticleEmitterSource` before `Transform`). Never scan
  `queryEach(Transform::class)` across the entire scene on a timer.
- **Keep off-screen, static, and interest-hidden entities asleep and excluded with `FamilySpec`.**
  In large streamed or networked worlds, attach a sleep tag/component to entities outside interest
  reach (and strip per-frame locomotion/controller components if the server owns their transforms).
  Hoist a reusable `FamilySpec` constant (`val AWAKE = FamilySpec.exclude(Asleep::class)` or
  `familySpec { all(...); exclude(...) }`) and iterate packed columns via
  `world.family(TYPE_A, TYPE_B, AWAKE)` or `Family1System` / `Family2System` (3.3–3.6× faster than
  unpacked `world.family { ... }` + `World.get`, and zero allocations on warmed worlds). Never use
  deprecated `familyExcluding(...)` or scan every entity in the world checking a boolean per frame.
- **Avoid megamorphic `process()` overhead on hot `IteratingSystem` / `Family1System` / `Family2System` subclasses.**
  When 3+ subclasses share the inherited `update()`, HotSpot stops inlining `process()` (~2.2–3.3×
  slower at 10k entities) and Wasm emits indirect `call_ref` per entity. Gate whole-tick early-outs
  with `shouldProcess(world, delta)` and forward hot subclasses through inline `runTick`:
  `override fun update(world: World, delta: Float) = runTick(world, delta) { e, a, b -> process(world, delta, e, a, b) }`.
- **Pass inline lambda literals to `queryEach` and `family.forEach`.** Never pass a function
  reference (`::step`) or `(Entity, A) -> Unit` value; non-inlined calls box every `Entity` handle
  on JVM, Android, and Wasm.
- **Use `EntityList` and `EntitySet` instead of `ArrayList<Entity>` / `HashSet<Entity>`.** Reuse
  primitive-backed `EntityList` scratch buffers (`clear()`, `add()`, inline `forEach`,
  `swapRemoveAt()`) as fields on the `System` instead of allocating a new collection per tick.
- Any deferred resolution loop (`unresolved > 0` waiting for async prefabs or parts) must carry a
  hard retry cap (`MAX_SEARCHES`) or exponential backoff. Without a cap, one empty or audio-only
  prefab turns a one-time lookup into a permanent periodic stutter.
- Early-out before touching HUD or world caches when zero entities match the active condition (for
  example, checking active sellers before scanning nameplate elements).

## 3. Per-frame GC traps in world-anchored HUD systems

- **Never `map.clear()` and re-put entries every frame.** Each `HashMap.put` allocates a fresh node
  (~32 B). For small fixed pools (`<= 32` nameplates), cache the `CanvasElement` references once at
  startup and scan the `ArrayList` directly — faster and **0 B/frame**.
- **Never scan `queryEach(Name::class, CanvasElement::class)` every frame.** Discover named HUD
  elements once per `World` and reuse the cached references.
- **Cache text measurements and formatted labels per slot.** Never call `measureTextWidth(...)`,
  allocate `"$label ($count)"`, or construct wrapper data classes every frame for unchanged plates;
  recompute only when `(text, look)` or `(entity, count)` changes.
- **Probe populated scenes, not only empty scenes.** An allocation probe with zero open signs,
  badges, or stacked drops reads 0 B/frame even while a crowded town churns GC every tick.

## 4. Mobile preset override ceilings

When a game sets `RenderQualitySettings.shadowBudgetOverride`, `effectQualityOverride`, or
dynamic resolution ranges on mobile tiers:

- Never let a mobile `Auto` / `Low` / `Medium` preset escalate above Core's mobile GPU budget
  (`ShadowBudget.Reduced`, 2 × 1024² cascades, 16-bit shadow depth) — reserve
  `ShadowBudget.Default` (3 × 2048²) for explicit `High` or desktop presets.
- Scale every spatial streamer's per-frame spawn budget (`modelsPerFrame`, `cellsPerFrame`) and
  active reach by graphics tier and view distance.
- Lock mobile tier ceilings (`cascades * mapSize²`, anisotropy, spawn caps, reach) with a unit test
  so future preset edits cannot regress mobile GPU cost silently.

## 5. Dense-world streaming budgets, shadow culling, and raycast picking

- **Share one per-frame node budget across overlapping cell streamers.** When multiple prop or
  clutter cell layers overlap (far/mid/near), drive them from a single coordinator using
  `BudgetedCellNodeSpawner.stepDespawns(remaining)` and `stepSpawns(remaining)` so crossing a
  multi-cell seam never multiplies node spawns by the number of layers.
- **Skip out-of-reach idle cell streamers in O(1).** Precompute each streamer's cell-center AABB
  bounds and skip observer updates when the camera is beyond `loadRadius` and no cells are active,
  waiting, or leaving.
- **Cap heavy terrain-surface spawns to 1 per frame.** Multi-area junctions can deliver multiple
  prefabs in one tick; drain at most one surface upload per frame so traversal stays hitch-free.
- **Retain recently evicted meshes and cull tiny/clutter shadow casters.** Configure tier-scaled
  `retainedMeshBudgetBytes` (preventing cell-seam GPU buffer re-upload churn) and
  `minShadowCasterRatio` on the scene app DSL, and disable `castsShadows` on near ground-clutter
  and grass-foliage layers while keeping architecture, trees, NPCs, and players casting shadows.
- **Exclude `StaticTransform` in per-frame mover picking.** Raycast picking over dynamic entities
  must query `world.family(TRANSFORM, MESH_BOUNDS, FamilySpec.exclude(StaticTransform::class))`
  with cached `ComponentType` / `ComponentTypeId` handles instead of scanning thousands of static
  scenery props every frame.
- **Guard perf invariants in unit tests.** Lock shared cell budgets, clutter shadow culling,
  1-surface/frame caps, retained mesh budgets, and zero allocating `.drainEffects()` / deprecated
  `familyExcluding(` usage with fast JVM tests so FPS regressions fail CI immediately.

## Idle HUD/window systems and per-system allocation gates

Every `System.update` runs every tick even when its window or panel is closed. Prevent steady-state
GC churn from creeping back into systems:

- **Early-return while closed and idle.** When a window/panel system is closed with no queued
  intents, no active drag/drop, and no open sub-sheet or mode, return before building view models,
  row/slot lists, or lookup helpers (keep only lightweight O(1) tracking that must observe
  background changes).
- **Project UI views only when inputs change.** Build derived view models or formatted HUD state
  strictly inside `if (next != current)` — or reuse the previous steady-state snapshot when all
  primitive stats, buffs, and trails are unchanged — never unconditionally on every frame. Skip
  `intents.toList()` when empty and guard empty drag queues before passing drop lambdas.
- **Watermark async/streaming attempts separately from rendered state.** When a system spawns or
  dresses streamed components (such as meshes whose renderer has not loaded yet), record the
  attempted version/appearance before skipping missing renderers so unloaded or headless entities do
  not re-run the full spawn/dress pass every tick.
- **Enforce a per-system idle allocation ceiling in CI.** Alongside a total systems ceiling, assert
  a tight per-system idle cap (e.g., `<= 1 KB/frame` per system under `-XX:-DoEscapeAnalysis`) so
  any newly added leaky system fails CI immediately and names the exact offending `*System` class.


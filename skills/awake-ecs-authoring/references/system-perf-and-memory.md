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

## 2. Narrow queries, excluded families, and unboxed entity bags

- Lead `queryEach` with the narrowest component (a player/active marker before `MovementControl`;
  `MeshRenderer` / `ParticleEmitter` / `ParticleEmitterSource` before `Transform`). Never scan
  `queryEach(Transform::class)` across the entire scene on a timer.
- **Keep off-screen and interest-hidden entities asleep and excluded.** In large streamed or
  networked worlds, attach a sleep tag/component to entities outside interest reach (and strip
  per-frame locomotion/controller components if the server owns their transforms). Iterate only
  active entities via `world.familyExcluding(A::class, B::class, Exclude::class)` (packed
  `Family1`/`Family2` with zero per-entity `World.get` lookups) or subclass `Family1System` /
  `Family2System` / `IteratingSystem` (which automatically cache and rebind the family on
  `World.generation` changes) — never scan every entity in the world and check a visibility boolean
  per frame.
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

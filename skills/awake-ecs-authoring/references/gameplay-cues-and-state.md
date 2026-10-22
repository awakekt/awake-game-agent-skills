# Gameplay State Decomposition, Animation Priority, and Audio Cues

Part of [awake-ecs-authoring](../SKILL.md). Read this reference before adding gameplay components,
combat/skill state, animation playback, or game audio systems.

---

## 1. Decompose God-Components and Replace `if/else` Chains with `EcsTag` Markers

### Anti-pattern: Object-Oriented God-Components
Do not pack stats, health, cooldowns, bitflags, hit lists, boolean animation flags
(`attackAnimationPending`, `skillAnimationPending`), and UI queues into a single 150-line
`Combatant` or `PlayerState` class. When everything lives on one component, every system queries the
entire world and runs nested `if (c.isDead) ... else if (c.isStunned) ...` branches.

### Correct pattern: Orthogonal Data Components + `EcsTag` State Markers

Split data by single responsibility and represent discrete states with singleton `EcsTag` markers so
`world.queryEach` and `world.family` filter entities at the storage level:

```kotlin
// 1. Focused data components
class Health(var current: Int = 100, var max: Int = 100) : Poolable {
    val isDead: Boolean get() = current <= 0
    override fun reset() { current = 100; max = 100 }
}

class CombatStats(
    var attack: Int = 10,
    var defense: Int = 0,
    var attackRange: Float = 2f,
    var attackSeconds: Float = 1.5f,
)

class CombatTarget(var entity: Entity? = null) : Poolable {
    override fun reset() { entity = null }
}

// 2. Payload-free EcsTag markers for state filtering
data object Dead : EcsTag
data object Stunned : EcsTag
data object InCombat : EcsTag
```

Now systems iterate only the entities whose state matches, eliminating deep `if/else` trees:

```kotlin
// RespawnSystem only visits entities carrying Dead — living entities are never branched on.
class RespawnSystem : System {
    override fun update(world: World, delta: Float) {
        val revived = ArrayList<Entity>()
        world.family(Dead::class, RespawnTimer::class).forEach { entity, _, timer ->
            timer.elapsed += delta
            if (timer.elapsed >= timer.durationSeconds) revived += entity
        }
        for (entity in revived) {
            world.remove<Dead>(entity)
            world.get<Health>(entity)?.let { it.current = it.max }
        }
    }
}
```

---

## 2. One-Shot Cues (`AnimationCue`, `SoundCue`), Never Boolean Polling or `HashMap` Diffing

### Anti-patterns to forbid
1. **Boolean flag polling on domain components**: Setting `combatant.attackAnimationPending = true`
   in `CombatSystem` and polling/clearing it in `CombatAnimationSystem`. If two systems read it or
   one runs out of order, cues are double-played or dropped.
2. **Diffing domain state in private `System` maps**: Storing `prevInventoryCount`, `prevCurrency`,
   or `attackSequences: HashMap<Entity, Long>` inside `GameAudioSystem` and reverse-engineering
   whether an item was picked up (`count > prevInventoryCount`) to trigger a sound effect.
3. **Side-table `HashMap<Entity, ...>` inside a God-System**: Keeping 10+ `HashMap`s inside a single
   700-line `NetClientSystem`. Store per-entity state on an ECS component (`NetworkReplicated`) and
   split independent concerns into separate systems (`NetSpawnSystem`, `RemoteInterpolationSystem`,
   `LocalReconciliationSystem`).

### Correct pattern: Typed Cue Queues Drained Once Per Frame

Attach a lightweight `PresentationCues` component (or world-level cue buffer) and emit typed sealed
events at the exact domain transition site:

```kotlin
sealed interface AnimationCue {
    data class Attack(val motionId: Int) : AnimationCue
    data class CastSkill(val skillId: String, val motionId: Int) : AnimationCue
    data object HitReact : AnimationCue
    data object Die : AnimationCue
    data object Respawn : AnimationCue
}

sealed interface SoundCue {
    data class MeleeSwing(val motionId: Int) : SoundCue
    data object HitImpact : SoundCue
    data object ItemPickup : SoundCue
    data class SkillCast(val skillId: String) : SoundCue
}

class EntityCues : Poolable {
    val animations = ArrayDeque<AnimationCue>()
    val sounds = ArrayDeque<SoundCue>()

    override fun reset() {
        animations.clear()
        sounds.clear()
    }
}

fun World.emitAnimation(entity: Entity, cue: AnimationCue) {
    ensure(entity, ::EntityCues).animations.addLast(cue)
}

fun World.emitSound(entity: Entity, cue: SoundCue) {
    ensure(entity, ::EntityCues).sounds.addLast(cue)
}
```

When loot is picked up or a strike lands, the domain system emits the cue directly:

```kotlin
// Inside LootSystem when an item is actually collected:
inventory.add(item)
world.emitSound(playerEntity, SoundCue.ItemPickup)
```

---

## 3. Declarative Animation Priority Table, Never Component Stashing

### Anti-patterns to forbid
1. **Stashing removed components in a `HashMap`**: Never rip `LocomotionAnimation` off a child
   entity on death and store it in `private val deadLocomotions = HashMap<Entity, LocomotionAnimation?>()`.
   If the entity despawns while dead, the map leaks; if two systems (`CombatSystem` and
   `CombatAnimationSystem`) both do it, they overwrite each other.
2. **String-prefix `if/else` chains**: Avoid scattering `if (clip.startsWith("skill-") || clip == "hurt")`
   across multiple systems.

### Correct pattern: Single `AnimationCueSystem` with Priority Resolution

Keep `LocomotionAnimation` attached to the entity, gate locomotion when `Dead` is present (or when a
higher-priority action clip is active), and resolve clips through a priority table in one system:

```kotlin
enum class AnimLayer(val priority: Int, val playback: AnimationPlayback) {
    LOCOMOTION(priority = 0, playback = AnimationPlayback.Loop),
    HIT_REACT(priority = 10, playback = AnimationPlayback.Once),
    ATTACK(priority = 20, playback = AnimationPlayback.Once),
    SKILL_CAST(priority = 30, playback = AnimationPlayback.Once),
    DEATH(priority = 100, playback = AnimationPlayback.Once),
}

data class ResolvedClip(val clipId: String, val layer: AnimLayer)

fun AnimationCue.resolveClip(): ResolvedClip = when (this) {
    is AnimationCue.Die -> ResolvedClip("die", AnimLayer.DEATH)
    is AnimationCue.CastSkill -> ResolvedClip("skill-$motionId", AnimLayer.SKILL_CAST)
    is AnimationCue.Attack -> ResolvedClip("attack-$motionId", AnimLayer.ATTACK)
    is AnimationCue.HitReact -> ResolvedClip("hurt", AnimLayer.HIT_REACT)
    is AnimationCue.Respawn -> ResolvedClip("stand", AnimLayer.LOCOMOTION)
}
```

`AnimationCueSystem` drains `EntityCues.animations`, picks the highest-priority `ResolvedClip`, and
Only interrupts the current clip when `incoming.layer.priority >= activeLayer.priority` or when the
current one-shot clip has finished (`player.isFinished`).

---

## 4. Spatial and One-Shot Audio with `:awake:scene:audio`

Awake provides `:awake:scene:audio` (`AudioSystem`, `AudioSource`, `AudioListener`, `SceneAudioSource`)
built on `:awake:core:audio` (`AudioPlayer`, `PositionalAudioMath`).

1. **Ambient and looping emitters**: Attach `AudioSource(clip, volume, loop = true, isSpatial3D = true)`
   to scene entities and `AudioListener()` to the active camera/player entity. Register Awake's
   `AudioSystem(audioPlayer, clips)` in the scene schedule—do not rewrite spatial distance
   attenuation or stereo panning by hand.
2. **One-shot gameplay SFX**: Drain `EntityCues.sounds` in a small `SoundCueSystem` that maps each
   `SoundCue` via a data table (`Map<KClass<out SoundCue>, AudioClip>` or sealed `when`) and plays
   3D positional sound at the entity's `Transform.position` (or 2D for UI/local pickup sounds).

---

## 5. Animation-Driven Audio Synchronization (`OnStart` / `OnHold` / `OnRelease` & Keyframe Markers)

### Never use `async` / `delay()` coroutines to sync sound with animation
A coroutine timer (`launch { delay(300); playSound() }`) runs on wall-clock time, while skeletal
animation runs on simulation time scaled by `player.speed` (`delta * player.speed`). Haste buffs,
frame hitches, or mid-cast interrupts (stun/death) immediately desync coroutine timers from the
rendered bone pose.

### Rules for frame-accurate audio-animation sync
1. **3-Phase Action Lifecycle (`OnStart` → `OnHold` → `OnRelease` / `OnCancel`)**:
   - **`OnStart` (Windup clip, `Once`)**: Plays the opening animation clip and emits `SoundCue.CastStart`.
   - **`OnHold` (Channeling loop clip, `Loop`)**: Entered when `OnStart` finishes while `skillCasting == true`.
     Emits `SoundCue.StartHoldLoop` so `AudioSystem` starts a looping `SoundHandle` tracked per
     entity.
   - **`OnRelease` / `OnCancel` (Release clip or Death/Stun interrupt)**: Emits `SoundCue.StopHoldLoop`
     (which calls `handle.stop()` on the active hold loop) before playing the release SFX.
2. **Timeline Keyframe Marker Crossing `(prevTime, currTime]`**:
   - Sub-clip events (melee whoosh at `t = 0.18s`, impact at `t = 0.36s`, left/right footsteps at
     `25%` and `75%` of `walk`/`run` clip duration) must be triggered when the `AnimationPlayer`'s
     playhead crosses the marker timestamp during `advance(delta * speed)`:

```kotlin
fun crossedMarker(
    prevTime: Float,
    currTime: Float,
    duration: Float,
    looping: Boolean,
    markerTime: Float,
): Boolean {
    if (duration <= 0f || markerTime !in 0f..duration) return false
    return if (!looping || currTime >= prevTime) {
        prevTime < markerTime && currTime >= markerTime
    } else {
        // Loop wrapped around duration -> 0f this frame
        prevTime < markerTime || currTime >= markerTime
    }
}
```

3. **Same-Frame ECS Schedule Order**:
   Run `GameplaySystems` → `AnimationSystem` (advances playhead, transitions `OnStart`/`OnHold`/`OnRelease`,
   and emits `SoundCue`s on marker crossings) → `AudioSystem` (drains `SoundCue`s in the same frame
   with zero-frame latency).


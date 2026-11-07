# Gameplay State Decomposition, Animation Priority, and Audio Cues

Part of [awake-ecs-authoring](../SKILL.md). Read this reference before adding gameplay components,
combat/skill state, animation playback, or game audio systems.

---

## 1. Decompose God-Components and Replace `if/else` Chains with `EcsTag` Markers

### Anti-pattern: Object-Oriented God-Components
Do not pack stats, health, cooldowns, bitflags, hit lists, boolean animation flags
(`attackAnimationPending`, `skillAnimationPending`), and UI queues into a single 150-line
combatant or player-state class. When everything lives on one component, every system queries the
entire world and runs nested `if (c.isDead) ... else if (c.isStunned) ...` branches.

### Correct pattern: Orthogonal Data Components + `EcsTag` State Markers

Split data by single responsibility and represent discrete states with singleton `EcsTag` markers so
`world.queryEach` and `world.family` filter entities at the storage level. Every type below is your
game's own; Awake supplies only `Poolable`, `EcsTag` and the storage:

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

## 2. One-Shot Cues, Never Boolean Polling or `HashMap` Diffing

### Anti-patterns to forbid
1. **Boolean flag polling on domain components**: Setting `attackAnimationPending = true` in a
   combat system and polling/clearing it in a combat animation system. If two systems read it or
   one runs out of order, cues are double-played or dropped.
2. **Diffing domain state in private `System` maps**: Storing `prevInventoryCount`, `prevCurrency`,
   or `attackSequences: HashMap<Entity, Long>` inside an audio system and reverse-engineering
   whether an item was picked up (`count > prevInventoryCount`) to trigger a sound effect.
3. **Side-table `HashMap<Entity, ...>` inside a God-System**: Keeping 10+ `HashMap`s inside a single
   700-line network client system. Store per-entity state on an ECS component and split independent
   concerns into separate systems (spawning, remote interpolation, local reconciliation).

### Correct pattern: Typed Cue Queues Drained Once Per Frame

Emit a typed cue at the exact domain transition site. Core has no animation cue type, so declare
your game's own and queue it on a small component. Sound already has a Core queue:
`AudioCueQueue` in `:awake:scene:audio`, filled by `World.emitAudioCue` and drained by
`AudioSystem`. Map your game's sound cues to clip paths and emit those:

```kotlin
// Your game's cue types and component. Not Awake types.
sealed interface AnimationCue {
    data class Attack(val motionId: Int) : AnimationCue
    data class CastSkill(val skillId: String, val motionId: Int) : AnimationCue
    data object HitReact : AnimationCue
    data object Die : AnimationCue
    data object Respawn : AnimationCue
}

sealed class SoundCue(val path: String) {
    data object MeleeSwing : SoundCue("sfx/melee-swing.wav")
    data object HitImpact : SoundCue("sfx/hit-impact.wav")
    data object ItemPickup : SoundCue("sfx/item-pickup.wav")
    data object CastRelease : SoundCue("sfx/cast-release.wav")
    data object FootstepLeft : SoundCue("sfx/footstep-left.wav")
}

class EntityCues : Poolable {
    val animations = ArrayDeque<AnimationCue>()

    override fun reset() {
        animations.clear()
    }
}

fun World.emitAnimation(entity: Entity, cue: AnimationCue) {
    ensure(entity, ::EntityCues).animations.addLast(cue)
}

// Core's emitAudioCue queues a OneShotAudioCue; maxDistance > 0 plays it as 3D sound.
fun World.emitSound(entity: Entity, cue: SoundCue, maxDistance: Float = 0f) {
    emitAudioCue(entity, cue.path, maxDistance = maxDistance)
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
   If the entity despawns while dead, the map leaks; if two systems (say, combat and combat
   animation) both do it, they overwrite each other.
2. **String-prefix `if/else` chains**: Avoid scattering `if (clip.startsWith("skill-") || clip == "hurt")`
   across multiple systems.

### Correct pattern: One Cue System with Priority Resolution

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

Your cue system drains `EntityCues.animations`, picks the highest-priority `ResolvedClip`, and
only interrupts the current clip when `incoming.layer.priority >= activeLayer.priority` or when the
current one-shot clip has finished (`AnimationPlayer.isFinished`).

---

## 4. Spatial and One-Shot Audio with `:awake:scene:audio`

Awake provides `:awake:scene:audio` (`AudioSystem`, `AudioSource`, `AudioListener`, `SceneAudioSource`,
`AudioCueQueue`) built on `:awake:core:audio` (`AudioPlayer`, `SoundHandle`, `PositionalAudioMath`).

1. **Ambient and looping emitters**: Attach `AudioSource(clip, volume, loop = true, isSpatial3D = true)`
   to scene entities and `AudioListener()` to the active camera/player entity. Register Awake's
   `AudioSystem(audioPlayer, clips)` in the scene schedule—do not rewrite spatial distance
   attenuation or stereo panning by hand.
2. **One-shot gameplay SFX**: Emit with `World.emitAudioCue` (or `AudioCueQueue.emit`). Each frame
   `AudioSystem` drains every queue. A cue with `maxDistance > 0` plays as 3D sound at the entity's
   `Transform.position`; otherwise it plays as 2D (UI and local pickup sounds). It plays only clips
   it was given, by path, so pass every cue clip in its `clips` map or its loads.

---

## 5. Animation-Driven Audio Synchronization (Start, Hold, Release and Keyframe Markers)

### Never use `async` / `delay()` coroutines to sync sound with animation
A coroutine timer (`launch { delay(300); playSound() }`) runs on wall-clock time, while skeletal
animation runs on simulation time scaled by `AnimationPlayer.speed`. Haste buffs, frame hitches,
or mid-cast interrupts (stun/death) immediately desync coroutine timers from the rendered bone pose.

### Rules for frame-accurate audio-animation sync
1. **Three-phase action lifecycle (start, hold, release or cancel) on ECS components**:
   - Store the phase (`ActionPhase` below) and the playhead you last saw (`lastObservedClipId`,
     `lastObservedClipTime`) on the entity's own components, never in `HashMap<Entity, ...>` side
     tables inside a `System`. Keep the looping hold sound in Core's
     `AudioCueQueue.activeHoldSound`.
   - **Start** (windup clip, `Once`): set `ActionPhase.ON_START`, play the opening clip, and emit
     the cast-start sound cue.
   - **Hold** (channeling clip, `Loop`): entered when the start clip finishes while the cast is
     still held. Set `ActionPhase.ON_HOLD`, play the looping clip, and start the looping sound
     with `AudioPlayer.playSound` (`loop = true`). Store its `SoundHandle` in `activeHoldSound`.
   - **Release or cancel** (release clip, or a death or stun interrupt): call
     `AudioCueQueue.stopHoldSound` first, then emit the release sound cue. `AudioCueQueue` is not
     `Poolable`, so stop the hold sound yourself before you destroy an entity mid-hold.

```kotlin
// Your game's phase enum. AudioCueQueue, emitAudioCue and playSound are Core.
enum class ActionPhase { IDLE, ON_START, ON_HOLD, ON_RELEASE, DEAD }

// Entering ON_HOLD: start the loop and keep its handle on the entity.
world.ensureAudioCueQueue(entity).activeHoldSound =
    audioPlayer.playSound(holdClip, loop = true)

// Leaving ON_HOLD for any reason (release, stun, death): stop the loop first.
world.get<AudioCueQueue>(entity)?.stopHoldSound()
world.emitSound(entity, SoundCue.CastRelease)
```

2. **Timeline Keyframe Marker Crossing `(prevTime, currTime]`**:
   - Sub-clip events (melee whoosh at 18% of the clip, impact at 36%, left/right footsteps at
     25% and 75% of a `walk`/`run` loop) fire when the `AnimationPlayer` playhead crosses the
     marker during `advance`. Use Core's `crossedTimelineMarker` (`:awake:core:animation`). It
     takes the marker as a normalized position and handles loop wrap-around:

```kotlin
val now = player.time
val duration = player.currentClip?.duration ?: 0f
if (crossedTimelineMarker(prevTime = lastTime, currTime = now, duration = duration,
        looping = true, markerNormalized = 0.25f)) {
    world.emitSound(entity, SoundCue.FootstepLeft)
}
lastTime = now
```

3. **Same-Frame ECS Schedule Order**:
   Run your gameplay systems, then Core's `AnimationSystem` (advances the playhead), then your
   system that reads the playhead, moves the phases and emits cues on marker crossings, then
   `AudioSystem` (drains the cue queues in the same frame, with zero-frame latency).
4. **Headless Audio & Cue Verification**:
   Verify cue emission, that the hold sound always stops on an interrupt, normalized marker
   crossings, and .ogg/.wav asset quality (earshot CLAP/Whisper/LUFS/loop-seam checks) using
   [awake-audio-verification](../../awake-audio-verification/SKILL.md).

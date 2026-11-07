---
name: awake-audio-verification
description: >
  Verify game audio assets (SFX, voice lines, music loops, ambience) and ECS audio synchronization
  (AudioCueQueue one-shot cues, start/hold/release cast-hold loops, animation timeline markers, and
  spatial AudioSystem calls) without human listening guesswork. Read before claiming an audio cue, cast-hold
  loop, animation keyframe sound, or generated/cooked .ogg/.wav asset works.
license: Apache-2.0
metadata:
  author: awake
  last-updated: '2026-11-07'
  keywords: Awake audio, AudioCueQueue, emitAudioCue, AudioSystem, AudioPlayer, NoOpAudioPlayer, SoundHandle, crossedTimelineMarker, ActionPhase, cast-hold loop, earshot, CLAP, LUFS, loop seam
---

# Awake Audio Verification

An audio feature or cooked sound asset is not verified because it compiled or because a file exists
on disk. Verify game audio across two deterministic layers without human listening guesswork:

1. **Deterministic ECS Audio Cue & Phase Sync Tests (`commonTest` / `jvmTest`)** — prove that the ECS emits the right sound cue on the exact simulation frame, scales with animation speed, and always stops looping `SoundHandle`s on interrupt.
2. **Perceptual & Technical Audio Asset QA (`earshot` CLI)** — prove that every `.ogg`/`.wav` file matches its semantic prompt, hits target LUFS loudness and peak headroom, contains no clipping or unintended silence, and loops cleanly without clicks.

Pairs with [awake-ecs-authoring](../awake-ecs-authoring/SKILL.md) and its
[gameplay-cues-and-state reference](../awake-ecs-authoring/references/gameplay-cues-and-state.md).

---

## Layer 1: Deterministic ECS Audio Cue & Phase Sync Tests

Never test game audio by launching a desktop window or waiting on wall-clock `delay()`. Drive the
ECS `World` with deterministic `delta` steps in `commonTest` and assert against the entity's
`AudioCueQueue` (`:awake:scene:audio`) and a recording player. Core has no public recording player:
extend Core's `NoOpAudioPlayer`, whose handles report `isPlaying` until `stop()`.

### 1. Assert the start, hold and release lifecycle and that the hold loop always stops

Every multi-phase action (e.g. a guardian's channeled fireball or charge skill) must be tested across
all four exit paths so the looping hold sound never leaks into an infinite orphan sound. The phases
are your game's `ActionPhase` values (see the
[gameplay-cues-and-state reference](../awake-ecs-authoring/references/gameplay-cues-and-state.md)):

| Scenario | Required Assertion |
|---|---|
| **Normal cast completion** | `ON_START` emits the cast-start cue; entering `ON_HOLD` starts a looping sound and stores its `SoundHandle` in `AudioCueQueue.activeHoldSound`; entering `ON_RELEASE` calls `AudioCueQueue.stopHoldSound` **before** it emits the release cue. |
| **Mid-cast stun / cancel** | Leaving `ON_HOLD` for `IDLE` or a hit reaction stops the handle and leaves `activeHoldSound` null on the same frame. |
| **Mid-cast death** | Dying (`ActionPhase.DEAD`) during `ON_START` or `ON_HOLD` stops `activeHoldSound` at once and emits the death cue. |
| **Despawn mid-hold** | `AudioCueQueue` is not `Poolable` and has no reset, so destroying the entity must call `stopHoldSound` first. Assert the handle stopped. |

```kotlin
// Your game's phases, as the reference declares them.
enum class ActionPhase { IDLE, ON_START, ON_HOLD, ON_RELEASE, DEAD }

// Your test fake: records what plays. NoOpAudioPlayer and its handles are Core.
class RecordingAudioPlayer : NoOpAudioPlayer() {
    val played = mutableListOf<String>()

    override fun playSound(clip: AudioClip, volume: Float, pan: Float, loop: Boolean): SoundHandle? {
        played += clip.id
        return super.playSound(clip, volume, pan, loop)
    }
}

@Test
fun interruptedHoldPhaseAlwaysStopsLoopingSoundHandle() {
    val world = World()
    val player = RecordingAudioPlayer()
    val entity = world.spawnCastEntity(skillId = "fireball") // your test helper

    // 1. Advance through the start phase into the hold loop
    stepCastPipeline(world, player, delta = 0.25f) // enters ON_HOLD
    val holdHandle = world.get<AudioCueQueue>(entity)?.activeHoldSound
    assertNotNull(holdHandle, "ON_HOLD must start and retain a looping SoundHandle")
    assertTrue(holdHandle.isPlaying)

    // 2. Interrupt the cast mid-hold with your game's stun tag
    world.add(entity, Stunned)
    stepCastPipeline(world, player, delta = 0.016f)

    // 3. The phase exit stopped the loop handle and cleared the reference
    assertFalse(holdHandle.isPlaying, "Interrupting ON_HOLD must call SoundHandle.stop()")
    assertNull(world.get<AudioCueQueue>(entity)?.activeHoldSound)
}
```

### 2. Assert normalized timeline markers (`marker.normTime`) across playback speeds

Sub-clip audio markers (melee swing whoosh at `normTime = 0.25f`, impact at `0.55f`, footsteps at
`0.25f` and `0.75f` of a `walk`/`run` loop) must be verified against `AnimationPlayer` playhead
crossings `(prevTime, currTime]`, as Core's `crossedTimelineMarker` checks them:

- **Single firing per pass**: Advancing in small steps (`16 ms`) or one large hitch step (`250 ms`) across `marker.normTime * duration` must emit the marker's sound cue **exactly once**.
- **Speed scaling**: At `player.speed = 2.0f` (haste) or `0.5f` (slow), the cue must fire at the scaled simulation time `(marker.normTime * duration) / speed`, proving no wall-clock timer is involved.
- **Loop wrap-around**: When a looping locomotion clip wraps from `0.95 * duration` past `duration` to `0.10 * duration` in a single tick, markers in both `(prevTime, duration]` and `(0f, currTime]` must fire without dropping or double-firing.

### 3. Verify 3D spatial routing with a recording player

Use the `RecordingAudioPlayer` above to verify `AudioSystem` without opening a hardware device:

- Assert that 3D emitters pass attenuated `volume` and stereo `pan` matching `PositionalAudioMath` for the listener's `Transform` and `AudioListener`.
- Assert that the same-frame schedule order (your gameplay systems, then `AnimationSystem`, then your cue system, then `AudioSystem`) drains `AudioCueQueue.pending` to empty by the end of the frame (zero-frame cue latency).
- Give `AudioSystem` every cue clip by path. It skips a queued cue whose clip it doesn't have.

---

## Layer 2: Perceptual & Technical Audio Asset QA (`earshot` CLI)

When generating, cooking, or importing `.ogg`/`.wav` assets (SFX, dialogue, ambient beds, or music
loops), inspect them headlessly with [`earshot`](https://github.com/tatsatx/earshot) — an
MIT-licensed local audio evaluation CLI powered by CLAP audio-text embeddings, Whisper
transcription, Silero VAD, and `ffmpeg`.

### 1. Install `earshot`

Install in an isolated tool environment (requires Python 3.11+ and `ffmpeg` on `PATH`):

```bash
uv tool install "earshot[all]"
# or:
pipx install "earshot[all]"
```

### 2. Verify semantic prompt match, artifacts, and transcripts (`earshot verify`)

Run `earshot verify` on every new or modified audio asset before committing:

```bash
# One-shot combat or spell SFX
earshot verify assets/audio/sfx/fireball_cast_start.ogg \
  --type sfx \
  --prompt "magic fire whoosh ignition cast start"

# Voice line with exact transcript verification
earshot verify assets/audio/voice/guardian_greeting.ogg \
  --type voice \
  --prompt "calm armored guardian speaking" \
  --transcript "Welcome to Harbor Town, traveler."

# Ambient environment bed or music cue
earshot verify assets/audio/ambience/harbor_docks_loop.ogg \
  --type ambience \
  --prompt "wooden dock waves gentle harbor wind"
```

What `earshot verify` checks and what to gate on:

- **Semantic similarity (CLAP)**: Confirms the rendered waveform actually sounds like `--prompt` (catches wrong asset exports, swapped filenames, or hallucinated TTS/SFX generations).
- **Signal integrity**: Flags unintended leading/trailing dead silence, digital clipping (`0 dBFS` flat-topping), DC offset, and clicks/pops.
- **Speech intelligibility (Whisper + Silero VAD)**: For `--type voice`, verifies word accuracy against `--transcript` and checks speech-to-silence ratio.

### 3. Inspect loudness (LUFS), peak headroom, and duration (`earshot info`)

```bash
earshot info assets/audio/sfx/melee_hit_heavy.ogg
```

Enforce consistent mix targets across the asset pack so runtime `AudioSource.volume` multipliers
behave predictably:

| Asset Category | Integrated Loudness Target | True Peak Ceiling | Duration / Tail Rules |
|---|---|---|---|
| **One-shot SFX (cast start, release, footsteps, UI)** | `-16` to `-12 LUFS` | $\le -1.0\text{ dBTP}$ | Trim leading silence $< 15\text{ ms}$ so cues feel immediate on keyframe crossings; decay tail cleanly to $-60\text{ dBFS}$. |
| **Hold sustain loops (channeling, beam, aura)** | `-18` to `-14 LUFS` | $\le -1.5\text{ dBTP}$ | Steady RMS envelope (`2.0s–6.0s`); zero leading/trailing silence. |
| **Voice / Dialogue** | `-18` to `-16 LUFS` | $\le -1.0\text{ dBTP}$ | Leading/trailing pad $50\text{–}150\text{ ms}$; zero clipping. |
| **Music & Ambience loops** | `-20` to `-14 LUFS` | $\le -1.0\text{ dBTP}$ | Seamless loop boundaries; no abrupt end cutoffs. |

### 4. Verify hold and music loop seams (`earshot loop`)

Any asset played with `loop = true` — especially `ActionPhase.ON_HOLD` channeling loops and ambient
beds — will click or pulse every cycle if its start and end zero-crossings or spectral envelopes
disagree. Check loop continuity before wiring the asset:

```bash
earshot loop assets/audio/sfx/fireball_cast_hold_loop.ogg
earshot loop assets/audio/music/harbor_town_theme.ogg
```

If `earshot loop` reports a seam discontinuity, leading/trailing silence, or a spectral jump across
the wrap point, fix the asset using an equal-power crossfade at a zero-crossing (via `ffmpeg`
`acrossfade` or DAW export) and re-run `earshot loop` until the seam passes cleanly.

### 5. Batch asset-cooking gate (`earshot batch`)

When importing or updating a pack of `.ogg`/`.wav` files, run batch verification across the manifest
or directory before opening a PR:

```bash
earshot batch assets/audio/manifest.json
```

---

## Verification Checklist

- [ ] `commonTest` covers the start, hold and release transitions and proves `AudioCueQueue.stopHoldSound` stops `activeHoldSound` on normal completion, stun/cancel interrupt, death, and despawn.
- [ ] Sub-clip keyframe markers (`normTime`) are tested across normal speed, scaled speed (`player.speed`), and loop wrap-arounds without wall-clock `delay()`.
- [ ] `AudioCueQueue.pending` is drained on the same frame it is emitted (gameplay systems, then `AnimationSystem`, then `AudioSystem`).
- [ ] Every new or updated `.ogg`/`.wav` asset passes `earshot verify` for its `--type` (`sfx`, `voice`, `music`, `ambience`) and `--prompt` (plus `--transcript` for voice).
- [ ] `earshot info` confirms LUFS loudness, true-peak headroom ($\le -1.0\text{ dBTP}$), and $< 15\text{ ms}$ leading onset for one-shot SFX.
- [ ] Every looping hold, ambience, and music asset passes `earshot loop` with no seam click or wrap-around gap.

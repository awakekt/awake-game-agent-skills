---
name: awake-camera-director
description: >
  Direct cinematic cameras, lighting, atmosphere, beat-synced audio/music, slow-motion speed ramps,
  scripted staging, and deterministic gameplay replay to generate storyboards and gameplay trailers
  with Awake's Director system (:awake:director, :awake:scene:director, and awake CLI/MCP tools).
  Use before writing a .director.json script, .reel.json trailer reel, in-game cutscene, storyboard
  preview, or headless trailer capture.
license: Apache-2.0
metadata:
  author: awake
  last-updated: '2026-11-23'
---

# Awake: Camera Director & Trailer Capture

Never direct a trailer by guessing raw world coordinates or exporting blind. Use Awake's closed
vibe-directing loop — stage inspection, schema validation, annotated storyboard contact sheets with
quantitative framing telemetry, and deterministic fixed-step video + WAV capture.

Full JSON/DSL blueprints and framing-warning fixes live in
[script-and-lighting-recipes.md](references/script-and-lighting-recipes.md).

## 1. Follow the Closed Directing Loop

1. **Inspect the stage on CPU first.** Run `awake stage <scene> --json` (or MCP `inspect_stage`) to
   discover composed world positions, forward vectors, lights, cameras, rails, stage markers, audio
   files, scripts, and recorded input takes. Never invent entity names or coordinates.
2. **Author intent, not brittle coordinates.** Write a `DirectorScript` (`*.director.json` or
   `directorScript { ... }`) or multi-scene `TrailerReel` (`*.reel.json`) using `FramingSpec`
   subjects, shot sizes, and angle presets.
3. **Validate on CPU before touching a GPU.** Run `awake director validate <file> --scene <scene>`
   (or MCP `validate_director`) to catch missing rails, cameras, subjects, audio clips, takes, or
   invalid lens ranges.
4. **Preview and fix warnings on a storyboard contact sheet.** Run
   `awake storyboard <scene> --director <file> --guides --json` (or MCP `preview_storyboard` /
   `preview_shot`). Inspect both the rendered PNG (Rule-of-Thirds grid, action-safe box, projected
   subject bounds, header badges) and `ShotFramingMetrics`. Eliminate occlusion, clipping, ground
   clearance, and exposure warnings before full capture.
5. **Capture deterministically.** Run `awake capture` (or MCP `capture_trailer`) at fixed step
   (`1f / fps`) with `OfflineAudioMixer` producing frame-locked video and 48 kHz stereo audio.

## 2. Frame by Intent and Optics

Describe *what* the viewer should feel using `FramingSpec` (`FramingSolver`) and `LensSpec`
(`CameraOptics`), instead of hardcoding eye/center vectors:

| Intent | `ShotSize` | `LensSpec` focal length | `AnglePreset` / Rig |
|---|---|---|---|
| Grand location reveal | `Establishing` / `Wide` | `24mm–35mm` | `High` / `Crane` / `SplineRail` |
| Hero introduction | `Full` / `Cowboy` | `35mm–50mm` | `LowHero` or `EyeLevel` + `Orbit` |
| Dialogue / emotion | `Medium` / `CloseUp` | `50mm–85mm` | `OverShoulderLeft` / `RuleOfThirdsLeft` |
| Climax tension / boss drop | `Medium` | `28mm → 85mm` | `DollyZoom` (`CameraOptics.dollyZoomDistance`) |
| High-speed chase | `Full` / `Wide` | `28mm–35mm` | `ChaseFollow` + `lookAheadSeconds` |

Rules:
- **Check low angles over wide ground.** `LowHero` and `WormsEye` use negative elevation angles; over
  large floors or docks the camera can dip below the surface. Verify `groundClearance` on the
  storyboard, enable `ShotCollisionSpec`, or supply a positive `elevationDeg`.
- **Keep rail speed constant.** Author reusable multi-point tracks as `SceneCameraRail` nodes
  (`ArcLengthSpline3f`) and reference them by `railName` in `ShotRigSpec.SplineRail`.
- **Add organic life sparingly.** Use `CameraFeelSpec` (`CameraFeelRig`) for subtle `handheldIntensity`
  (`0.08–0.20`), damped follow (`smoothTime`), and beat-triggered `ActionCueSpec.CameraTrauma`
  impulses (`0.25–0.65`) on impacts rather than constant heavy shake.

## 3. Orchestrate Lighting, Atmosphere, and Audio on the Beat

A static flat-lit camera move looks like a debug viewer. Layer `lightingTrack`, `audioTrack`, and
`music` onto a shared `BeatClock`:

- **Lock cuts and accents to music.** Set `BeatClock` (`bpm`, `beatsPerBar`, `offsetSeconds`) and
  express shot durations and cue triggers with `DurationRef` / `TimeRef` in beats so cuts, flashes,
  and speed ramps land directly on downbeats.
- **Shape silhouette and mood dynamically.** Combine:
  - `LightingCueSpec.DayCycleSweep` to move the sun and shadow angles across a shot.
  - `LightingCueSpec.HeroRimLight` to spawn a camera-relative practical rim light separating the
    hero from dark backgrounds.
  - `LightingCueSpec.LightFlash` for exponential-decay lightning or spell impacts (optionally
    boosting sun intensity).
  - `LightingCueSpec.DirectionalLight`, `LightingCueSpec.FogRamp`, and `LightingCueSpec.ColorGrade`
    for contrast, saturation, white balance, and bloom shifts. `DirectorSystem` always applies
    `ToneMappingMode.Passthrough` on `ToneMappingGradeEffect` so lit scene color is never double
    tone-mapped.
- **Mix audio deterministically.** `OfflineAudioMixer` implements `AudioPlayer` and mixes in-game
  3D `AudioSystem` sounds, `AudioCueSpec.PlaySfx` cues, and `MusicTrackSpec` into one synced 48 kHz
  stereo WAV. Use `duckMusicGain` on impact SFX so stingers cut cleanly through the music bed, and
  set `TrailerReel.music` to carry one uninterrupted soundtrack across multi-scene cuts.
- **Verify source audio quality.** Pair with
  [awake-audio-verification](../awake-audio-verification/SKILL.md) to validate `.wav`/`.ogg`
  loudness, loop seams, and zero clipping before mixing.

## 4. Combine Live Gameplay Replay and Scripted Action

Trailers look authentic when real gameplay runs beneath cinematic angles:

- **Record once, re-shoot from any angle.** Capture live play with `InputRecordSystem` into an
  `InputTake` (`*.take.json`), then replay it through `InputReplaySystem` (`--take <file>` or
  `DirectorScript.inputTake`).
- **Camera-basis isolation is automatic.** `DirectorSystem` implements `UnscaledSystem` and owns a
  dedicated primary `Camera` + `AudioListener` while leaving the player's `CameraRig` on
  `ActiveCamera`. Because `CameraRelativeBasis` reads `ActiveCamera`, the player follows the exact
  recorded path no matter where the director flies, while 3D audio spatializes from the directed
  lens.
- **Use speed ramps without stalling the camera.** `ActionCueSpec.TimeScaleRamp` drives
  `SceneSchedule.timeScale` (`0f` hitstop freeze → slow-mo hold → ease back to `1f`) and scales SFX
  pitch via `OfflineAudioMixer` while `DirectorSystem` continues orbiting smoothly at full unscaled
  frame rate.
- **Stage non-player beats with `actionTrack`.** Trigger `ActionCueSpec.InputAction`,
  `ActionCueSpec.ActorMove` (targeting coordinates or `SceneStageMarker` nodes),
  `ActionCueSpec.PlayAnimation`, and `ActionCueSpec.ParticleBurst` on exact timestamps or beats.
- **Embed in-game cutscenes cleanly.** Attach `SceneCameraDirector`, `SceneVirtualCamera`,
  `SceneCameraRail`, and `SceneStageMarker` in `.scene.json`, or pass `DirectorRuntimeOverride` to
  `runProject` for external trailer scripts without editing scene files.

## 5. Export Formats and Delivery Presets

Choose the preset matching the target channel:

| `--preset` | Size | FPS | Use for |
|---|---|---|---|
| `youtube-1080p` | `1920x1080` | `60` | Full gameplay trailer / store page video |
| `youtube-720p` | `1280x720` | `60` | Fast review cut / PR video attachment |
| `shorts-1080p` | `1080x1920` | `60` | Vertical shorts / mobile portrait promos |
| `cinemascope-1080p` | `1920x804` | `24` | Widescreen 2.39:1 teaser / announcement |
| `gif-preview` | `640x360` | `24` | Compact looping preview GIF |

- Pass `--hud hide` (or `hudVisible = false` per shot) for a clean trailer feed, or `hudVisible = true`
  on dedicated gameplay-UI beats.
- Output format is inferred from `--output` (`.mp4`, `.webm`, `.gif`, or a directory for
  `png-sequence` + `audio.wav`). Use `--keep-frames` only when inspecting individual frames.
- For PR motion proof clips under 1 MB, also follow
  [awake-gif-evidence](../awake-gif-evidence/SKILL.md).

## Verification Checklist

- [ ] Inspected the target scene with `awake stage` / `inspect_stage` so every referenced subject,
      rail, camera, marker, take, and audio path exists.
- [ ] Passed `awake director validate` / `validate_director` with 0 errors and reviewed all warnings.
- [ ] Reviewed an annotated `awake storyboard --guides` / `preview_storyboard` contact sheet and
      resolved unintended occlusion, clipping, dark/blown-out luminance, or ground-clearance issues.
- [ ] Confirmed `awake capture` produced moving frames and non-silent synced audio (`audioPeakAmplitude > 0`
      when soundtrack/SFX are authored) and visually watched the rendered output before sharing.

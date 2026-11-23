# Camera Director Recipes & Telemetry Remediation

Reference recipes for `:awake:director`, `:awake:scene:director`, and `awake` CLI / MCP trailer
workflows. Every JSON discriminator below matches `DirectorScript.json` (`classDiscriminator = "type"`).

## 1. Three-Act Gameplay Trailer Pacing Blueprint

| Act | Duration (at 120 BPM) | Camera & Lens | Lighting & Audio |
|---|---|---|---|
| **Act 1 — Hook / World** | `4–8` beats (`2–4s`) | `Establishing` or `Wide`, `24–35mm`, `SplineRail` or `Crane` | `DayCycleSweep` + music fade-in + ambient SFX |
| **Act 2 — Gameplay & Character** | `8–16` beats (`4–8s`) | `Full` / `Medium`, `35–50mm`, `Orbit` + `ChaseFollow` over recorded `InputTake` | `HeroRimLight` + beat-locked `HardCut`s + 3D combat SFX |
| **Act 3 — Climax Beat Drop** | `4–8` beats (`2–4s`) | `DollyZoom` (`28mm → 85mm`) or `WhipPan` + `TimeScaleRamp` slow-mo | `LightFlash` + `CameraTrauma` + `PlaySfx` with `duckMusicGain = 0.25` |
| **Outro — Clean Hold** | `2–4` beats (`1–2s`) | `Static` or gentle `Dolly` pull-back with `FadeThroughBlack` | Music `fadeOutSeconds`, calm exposure & bloom settle |

## 2. Exact JSON Type Discriminators (`*.director.json`)

| Family | `@SerialName` (`"type"`) values |
|---|---|
| `ShotTransitionSpec` | `"cut"`, `"blend"`, `"fade_black"` |
| `ShotRigSpec` | `"static"`, `"orbit"`, `"dolly"`, `"crane"`, `"spline_rail"`, `"chase_follow"`, `"dolly_zoom"`, `"whip_pan"`, `"named_camera"` |
| `LightingCueSpec` | `"day_cycle_sweep"`, `"directional_light"`, `"hero_rim_light"`, `"light_flash"`, `"fog_ramp"`, `"color_grade"` |
| `AudioCueSpec` | `"play_sfx"`, `"music_control"` |
| `ActionCueSpec` | `"input_action"`, `"actor_move"`, `"play_animation"`, `"particle_burst"`, `"time_scale"`, `"trauma"` |
| `ShotSize` | `"extreme_close_up"`, `"close_up"`, `"medium_close_up"`, `"medium"`, `"cowboy"`, `"full"`, `"wide"`, `"establishing"` |
| `AnglePreset` | `"worms_eye"`, `"low_hero"`, `"eye_level"`, `"high"`, `"birds_eye"`, `"over_shoulder_left"`, `"over_shoulder_right"`, `"profile_left"`, `"profile_right"` |
| `ScreenComposition` | `"center"`, `"rule_of_thirds_left"`, `"rule_of_thirds_right"` |

## 3. Worked `*.director.json` Script

```json
{
  "version": 1,
  "name": "harbor_launch_trailer",
  "clock": { "bpm": 120.0, "beatsPerBar": 4, "offsetSeconds": 0.0 },
  "inputTake": "takes/harbor_combat.take.json",
  "music": {
    "path": "audio/theme.wav",
    "volume": 0.8,
    "fadeInSeconds": 0.3,
    "fadeOutSeconds": 0.8
  },
  "shots": [
    {
      "id": "golden_orbit",
      "duration": { "beats": 4.0 },
      "lens": { "focalLengthMm": 50.0 },
      "rig": {
        "type": "orbit",
        "framing": {
          "subjects": ["Hero"],
          "shotSize": "medium",
          "angle": "eye_level",
          "azimuthDeg": 165.0,
          "elevationDeg": 8.0,
          "composition": "rule_of_thirds_left"
        },
        "startAzimuthDeg": -30.0,
        "endAzimuthDeg": 30.0,
        "startRadiusMultiplier": 1.15,
        "endRadiusMultiplier": 0.92,
        "easing": "EaseInOutSine"
      },
      "feel": { "handheldIntensity": 0.12, "smoothTime": 0.06 }
    },
    {
      "id": "crane_reveal",
      "duration": { "beats": 4.0 },
      "lens": { "focalLengthMm": 35.0 },
      "transitionIn": { "type": "blend", "duration": { "seconds": 0.45 }, "easing": "EaseInOutCubic" },
      "rig": {
        "type": "crane",
        "framing": {
          "subjects": ["Hero", "BeaconTower"],
          "shotSize": "full",
          "angle": "high",
          "azimuthDeg": 185.0,
          "elevationDeg": 14.0
        },
        "startHeightDelta": 0.4,
        "endHeightDelta": 4.0,
        "easing": "EaseInOutCubic"
      }
    },
    {
      "id": "dolly_zoom_finale",
      "duration": { "beats": 4.0 },
      "transitionIn": { "type": "cut" },
      "rig": {
        "type": "dolly_zoom",
        "framing": {
          "subjects": ["Hero"],
          "shotSize": "medium",
          "angle": "eye_level",
          "azimuthDeg": 180.0,
          "elevationDeg": 5.0
        },
        "startFocalLengthMm": 28.0,
        "endFocalLengthMm": 85.0,
        "easing": "EaseInOutCubic"
      }
    }
  ],
  "lightingTrack": [
    {
      "type": "day_cycle_sweep",
      "at": { "seconds": 0.0 },
      "duration": { "beats": 8.0 },
      "fromTime": 0.24,
      "toTime": 0.48
    },
    {
      "type": "hero_rim_light",
      "at": { "seconds": 0.0 },
      "duration": { "beats": 4.0 },
      "subject": "Hero",
      "color": { "r": 1.0, "g": 0.78, "b": 0.45 },
      "intensity": 5.5,
      "distance": 4.5,
      "heightOffset": 2.4,
      "range": 14.0
    },
    {
      "type": "light_flash",
      "at": { "beat": 8.2 },
      "duration": { "seconds": 0.7 },
      "subject": "Hero",
      "peakIntensity": 8.0,
      "boostSunIntensity": 1.4,
      "range": 18.0
    }
  ],
  "audioTrack": [
    {
      "type": "play_sfx",
      "at": { "beat": 8.2 },
      "path": "audio/impact_boom.wav",
      "volume": 0.95,
      "duckMusicGain": 0.25,
      "duckHoldSeconds": 0.5
    }
  ],
  "actionTrack": [
    {
      "type": "time_scale",
      "at": { "beat": 8.2 },
      "hitstopSeconds": 0.06,
      "rampInSeconds": 0.1,
      "holdSeconds": 0.65,
      "rampOutSeconds": 0.3,
      "targetScale": 0.25,
      "pitchShiftAudio": true
    },
    {
      "type": "trauma",
      "at": { "beat": 8.2 },
      "amount": 0.45,
      "decaySeconds": 0.6
    }
  ]
}
```

## 4. Multi-Scene `*.reel.json` Recipe

A `TrailerReel` shares one continuous `OfflineAudioMixer` soundtrack across multiple scenes:

```json
{
  "version": 1,
  "name": "harbor_full_trailer",
  "clock": { "bpm": 120.0, "beatsPerBar": 4 },
  "music": {
    "path": "audio/main_theme.wav",
    "volume": 0.8,
    "fadeInSeconds": 0.4,
    "fadeOutSeconds": 1.2
  },
  "segments": [
    { "id": "intro", "scene": "scenes/harbor.scene.json", "directorPath": "scripts/intro.director.json" },
    { "id": "combat", "scene": "scenes/arena.scene.json", "directorPath": "scripts/combat.director.json", "inputTake": "takes/arena_combo.take.json" }
  ]
}
```

## 5. Kotlin DSL & In-Game Cutscene Wiring

```kotlin
val cutscene = directorScript("harbor_intro") {
    bpm(120f)
    music("audio/theme.wav", volume = 0.75f, fadeInSeconds = 0.3f, fadeOutSeconds = 0.8f)
    shot("hero_orbit") {
        beats(4f)
        lens(focalLengthMm = 50f)
        orbit("Hero", startAzimuthDeg = -30f, endAzimuthDeg = 30f, shotSize = ShotSize.Full)
        feel = CameraFeelSpec(handheldIntensity = 0.12f, smoothTime = 0.06f)
    }
    lighting(
        LightingCueSpec.HeroRimLight(
            at = TimeRef.beat(0f),
            duration = DurationRef.beats(4f),
            subject = "Hero",
            intensity = 5f,
        ),
    )
    action(ActionCueSpec.CameraTrauma(at = TimeRef.beat(2f), amount = 0.35f))
}
```

To drive any loaded project externally without editing its `.scene.json` files (such as in a headless
test or custom capture tool), pass `DirectorRuntimeOverride` into `runProject`:

```kotlin
val override = DirectorRuntimeOverride(
    script = cutscene,
    inputTake = recordedTake,
    audioPlayer = OfflineAudioMixer(),
    extraAudioClips = decodedClips,
)
app { scene("trailer") { runProject(loadedProject, directorOverride = override) } }
```

## 6. Fixing `ShotFramingMetrics` Warnings

| Warning from `FramingAnalyzer` | Root cause | Fix |
|---|---|---|
| `sightline is X% occluded by '<Node>'` | A physics collider sits between eye and subject | Rotate `azimuthDeg` around the obstacle, raise `elevationDeg`, or enable `ShotCollisionSpec` (`obstacleLayers`). |
| `clipped on edge(s): left/right/top/bottom` | Subject bounds extend past viewport border (often mid-blend or too tight `ShotSize`) | Widen `ShotSize` (e.g. `Medium` → `Full`), shorten `SmoothBlend` duration, or switch to `HardCut` on large framing jumps. |
| `too close to or below terrain` | Negative elevation angle dipped eye under ground/floor | Increase `elevationDeg`, add `ShotCollisionSpec(ground = true, groundMargin = 0.4f)`, or raise `startHeightDelta`. |
| `Frame appears very dark` / `blown out` | Missing/dim lights or stacked `LightFlash` + high exposure | Add `HeroRimLight` or raise `DirectionalLight.intensity`; lower `LightFlash.peakIntensity` or `ColorGrade.exposure`. |
| `fills X% height (crowded / expected ~Y%)` | Explicit `distanceOverride` or `radiusMultiplier` disagrees with target `ShotSize` | Remove `distanceOverride` to let `FramingSolver` auto-fit, or adjust `shotSize` / `focalLengthMm`. |

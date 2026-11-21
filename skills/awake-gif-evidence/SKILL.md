---
name: awake-gif-evidence
description: Turn a headless Awake test run into an animated GIF that proves a change in motion (a walk, a camera, an aim, a flight, a window animating), with a before clip for a fix. Use when a still screenshot can't show the claim, before attaching evidence to a pull request, or when asked for a GIF or a clip of a test.
license: Apache-2.0
metadata:
  author: awake
  last-updated: '2026-11-21'
---

# Awake: GIF Evidence

A still frame proves a layout. Motion needs frames over time: a character that circles a spot, a
camera that shakes, a ride that snaps back, an aim that points the wrong way. A GIF of the test that
asserts the behaviour shows a reviewer what the numbers measured.

## When to make one

| The claim is about | Evidence |
|---|---|
| Where something is drawn, its size, its theme | A still screenshot |
| How something moves or changes over frames | A GIF, plus the measured figure |
| A bug that shows in motion | Two GIFs: before (on the base branch) and after |
| Timing alone (a gauge filling, a cooldown) | A GIF, or three stills at named times |

A GIF never replaces the assertion. It comes from the same run as a test that fails when the
behaviour is wrong, and the pull request states the figure that test measured (for example
"camera back-steps: 57 before, 0 after").

## Capture the frames

Capture headless, on the same backend the test uses. Lavapipe draws a Vulkan frame on a machine
with no GPU.

1. Create the engine on a `HeadlessSurface` at the evidence size (640x360 or 854x480; a phone
   layout at its own size).
2. Step the scene with a fixed delta, `1f / fps`, never the wall clock. The clip is then the same on
   every run, and a slow machine records the same motion as a fast one.
3. After each step, draw and read the frame back with `GraphicsEngine.readPresentedPixels` (or
   `Renderer.readPresentedPixels`). The `TextureAsset` it returns is tightly packed RGBA8, `width`
   by `height`.
4. Write each frame as `frame-0000.png`, `frame-0001.png`, ... into one directory per clip. On the
   JVM, `BufferedImage` and `ImageIO` write a PNG with no new dependency.
5. Read back every Nth step rather than every step when the simulation runs faster than the clip:
   at 60 steps a second, every 4th step gives 15 fps.

Rules for the run:

- Record the frames inside the test that asserts the behaviour, behind a switch (a system property
  or an environment variable), so a normal run writes nothing and costs nothing.
- Keep a clip short: 2 to 6 seconds, 30 to 90 frames. Crop to the region that moves when it is
  small on screen.
- Hold the first and last frames for half a second so a looping GIF reads as start and end.
- Draw no debug overlay the claim doesn't need. If the overlay is the evidence (a route, a hit box),
  say so in the caption.
- For a before clip, run the same test on the base branch with the fix reverted, at the same size,
  seed and step.

## Encode the GIF

Use an existing encoder; don't write one.

- `gifski` (preferred): high quality and small, from the PNG frames.

  ```bash
  gifski --fps 15 --width 640 --quality 80 -o walk-after.gif frames/frame-*.png
  ```

- `ffmpeg` (fallback): two passes through a palette, or the colours band.

  ```bash
  ffmpeg -y -framerate 15 -i frames/frame-%04d.png \
    -vf "scale=640:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4" \
    walk-after.gif
  ```

Limits:

| Setting | Value |
|---|---|
| Frame rate | 12 to 15 fps |
| Width | 480 to 640 px (a phone layout: its height at 640 px or less) |
| Size | under 10 MB, the pull request attachment limit; aim for under 3 MB |
| Loop | forever (both encoders' default) |

Over the limit: lower the width, then the frame rate, then crop, then shorten. Never lower the
quality until the motion the clip proves is lost to banding.

## Attach it

- Commit the clip only where the project keeps design evidence (for example a `docs/design/<feature>/`
  folder), and keep the frames out of the repository.
- In the pull request body, put the clip under the measured figure, before and after side by side:

  ```markdown
  | Before | After |
  |---|---|
  | ![before](https://github.com/OWNER/REPO/raw/BRANCH/docs/design/click-walk/walk-before.gif) | ![after](https://github.com/OWNER/REPO/raw/BRANCH/docs/design/click-walk/walk-after.gif) |
  ```

- Caption each clip with what to watch and the figure: "Clicking 0.5 m from the feet: the character
  circles and the camera back-steps 57 times in 3 s. After: it turns once and stops, with 0
  back-steps."
- A clip that shows nothing wrong in the before case proves nothing. Reproduce the bug in the clip,
  or say the before clip is missing and why.

## Check before posting

- Open the GIF and watch it through once. Confirm it shows the claimed motion, not a still frame or
  a black one, which a read before the first draw returns.
- Confirm the before and after clips use the same size, step and starting state.
- See
  [awake-render-headless-verification](https://github.com/awakekt/awake-agent-skills/blob/main/skills/awake-render-headless-verification/SKILL.md)
  for proving a headless run really ran, and
  [awake-render-debug-views](../awake-render-debug-views/SKILL.md) when the clip should show what a
  shader computed.

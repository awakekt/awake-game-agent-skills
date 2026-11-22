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
   at 60 steps a second, every 5th step gives 12 fps.

Rules for the run:

- Record the frames inside the test that asserts the behaviour, behind a switch (a system property
  or an environment variable), so a normal run writes nothing and costs nothing.
- Keep a clip short: 2 to 5 seconds, 24 to 60 frames. Crop to the region that moves when it is
  small on screen.
- Hold the first and last frames for half a second so a looping GIF reads as start and end.
- Draw no debug overlay the claim doesn't need. If the overlay is the evidence (a route, a hit box),
  say so in the caption.
- For a before clip, run the same test on the base branch with the fix reverted, at the same size,
  seed and step.

## Encode the GIF

Use existing tools; don't write an encoder. Small is the default: a reviewer's page loads every clip.

1. **Encode** from the PNG frames at 12 fps, 480 px wide, 128 colours, no dither. Dither noise
   changes every frame and defeats the GIF's frame-to-frame compression.

   - `gifski` (preferred):

     ```bash
     gifski --fps 12 --width 480 --quality 70 -o walk-after.gif frames/frame-*.png
     ```

   - `ffmpeg` (fallback): two passes through a palette that only counts what changes:

     ```bash
     ffmpeg -y -framerate 12 -i frames/frame-%04d.png \
       -vf "fps=12,scale=480:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=none:diff_mode=rectangle" \
       walk-after.gif
     ```

2. **Shrink** it with `gifsicle`, which keeps only each frame's changed rectangle and drops detail the
   eye doesn't see:

   ```bash
   gifsicle -O3 --lossy=80 walk-after.gif -o walk-after.gif
   ```

Measured on 60 frames of a rider over a phone HUD: the earlier 15 fps, 640 px, 256-colour dithered
GIF was 676 KB; these settings make 360 KB, and `gifsicle` 272 KB.

Limits:

| Setting | Value |
|---|---|
| Frame rate | 10 to 12 fps; 15 only when the claim is about smoothness |
| Width | 480 px (a phone layout: its height at 480 px or less); 640 px only for small text |
| Colours | 128; 64 for flat UI |
| Size | under 1 MB each; never over 3 MB |
| Loop | forever (both encoders' default) |

Over the limit, in this order: crop to the region that moves, shorten the clip, lower the frame
rate, lower the width, then `--lossy=120`. Stop before the motion the clip proves is lost.

**Still over 1 MB:** post an MP4 instead. The same clip as H.264 at 480 px was 76 KB, and GitHub plays an
MP4 dropped into a pull request inline:

```bash
ffmpeg -y -framerate 12 -i frames/frame-%04d.png -vf "scale=480:-2" \
  -c:v libx264 -pix_fmt yuv420p -crf 28 -movflags +faststart walk-after.mp4
```

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

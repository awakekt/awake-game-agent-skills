---
name: awake-render-debug-views
description: Look inside an Awake 3D frame instead of guessing. Switch the scene shaders to world normals, linear depth, cascade-tinted shadow visibility, albedo, terrain layer weights, dominant layer or lightmap, or view the real shadow map. Use when shadows are missing, clipped, speckled or misplaced, a surface has the wrong colour or shading, terrain looks wrong after an import, or before tuning any shading constant.
license: Apache-2.0
metadata:
  author: awake
  last-updated: '2026-10-03'
---

# Awake Render: Debug Views

Every Awake scene shader can draw what it computed instead of its lit colour. Look first, then
tune: one frame of the right view answers what a constant sweep only guesses at.

## Pick the view from the symptom

| Symptom | View | What it tells you |
|---|---|---|
| Shadows stop partway into the scene | `ShadowVisibility` | Grey where the cascade tints end is the shadow distance (100 units by default), not a sampling bug |
| Speckle, detached or floating shadows | `ShadowVisibility`, then `ShadowMap` | Speckle inside one tint is bias; a caster absent from `ShadowMap` never reached the depth pass |
| Shadow quality jumps along a line | `ShadowVisibility` | A tint boundary is a cascade split |
| Faceted, inverted or flat lighting | `WorldNormals` | Whether the normal the shader actually shades with is the one you expect |
| Wrong colour | `Albedo` | Right albedo points at lighting or fog; wrong albedo points at material, texture or vertex colour |
| Far clipping, fog or depth-based effects | `LinearDepth` | Real view distance per pixel against the far plane |
| Terrain paints the wrong material, mirrored or shifted | `DominantLayer`, `LayerWeights` | Which palette layer wins where, and how layers blend |
| Terrain too dark or bright, or baked shadows misplaced | `Lightmap` | The bake exactly as stored, before lighting |

## Turn one on

For the whole scene, at runtime:

```kotlin
world.debugSettings().apply {
    renderDebugView = RenderDebugView.ShadowVisibility
    renderDebugLayer = 0 // ShadowMap only
}
```

`RenderDebugView.Off` restores the lit image. For a pass you compile yourself, pass
`EnvironmentUniforms(debugView = ..., debugLayer = ...)` to `ScenePassCompiler.compile`.

- `ShadowMap` draws only when the app's `RenderPlan` lists `shadowMapViewContentFeature()` in
  `contentFeatures`. Its layers are the cascades first, then six faces per shadowed point light
  from `PointShadowLight.baseLayer`. A negative layer draws an empty map.
- An extra view (an editor preview, a render-to-texture camera) must compile its own light:
  `SceneViewLighting(renderer.clipSpace).light(world, camera, aspect)` fits cascades to that
  camera. With no light the pass renders the default light and no shadow pass, and every shadow
  view reads grey.

## Read the colours

| View | Encoding |
|---|---|
| `WorldNormals` | `n * 0.5 + 0.5`: up is green (128, 255, 128), +Z light blue (128, 128, 255), +X pink (255, 128, 128) |
| `LinearDepth` | Depth along the camera's forward axis: black at the eye, white at the lens `far` |
| `ShadowVisibility` | Cascade 0 red, 1 green, 2 blue, 3 yellow, darkened to a quarter where shadowed; grey where no cascade answered |
| `Albedo` | Surface colour in the space the shader writes its lit colour |
| `LayerWeights` | Each palette layer in its own colour (0 red, 1 green, 2 violet), mixed by weight |
| `DominantLayer` | The strongest layer's colour, unmixed |
| `Lightmap` | The stored bake; mid grey is x1 |
| `ShadowMap` | One depth layer: black at the light, white where nothing was drawn. The screen is the layer's own light-space NDC, not the camera's view |

**Grey also means "no data".** A shader without what a view needs draws mid grey: textured PBR
under `ShadowVisibility` (it does not receive shadows), and any non-terrain mesh under the layer
views. A grey mesh inside the tinted band therefore does not sample shadows at all.

Not covered: the non-instanced skinned shaders still draw lit. The sky and depth fog switch off
while a view is on, since they would paint over the data.

## Make a new scene shader honour the views

- Route the fragment output through the shader pack's
  `debugViewColor(debugView, cameraPosition, DebugSurface(...), lit)`. Fill only the
  `DebugSurface` fields the shader really has; the helper decides what every view shows.
- Append `UniformFields.DebugView` to the end of the uniform layout, which keeps a depth pass's
  prefix struct intact. Write it with `putDebugView(view, cameraForward)` from `render:passes`.
- A shader calling `cascadeShadowSampling` must pass `shadowCascade(world)` as
  `DebugSurface.shadowCascade`; ASL rejects the unused function otherwise.
- A new view is a new `RenderDebugView` entry whose `code` is never reused (it is shader ABI),
  plus one line in `debugViewColor`. Backends only forward `GpuDebugView`; never branch on a view
  there. See [render pipeline](https://github.com/awakekt/awake-agent-skills/blob/main/skills/awake-render-pipeline/SKILL.md) for that boundary.

## Prove a view, or a fix a view found

A view is measurable, so assert numbers rather than impressions
([headless verification](https://github.com/awakekt/awake-agent-skills/blob/main/skills/awake-render-headless-verification/SKILL.md)):

- Compute on the CPU what the view must show from the same inputs: a ground raycast for
  `LinearDepth`, the cascade matrix for `ShadowMap`, the layer colour formula for the terrain
  views. Compare per pixel within a few units. WebGPU's offscreen target is sRGB, so decode its
  stored bytes first.
- Run the identical check on the lit frame, the wrong layer or a shadows-off pass. It must fail;
  a check the lit frame passes measures nothing.
- Worked examples in Awake: `SceneDebugViewParityTest` (both backends),
  `RendererHeadlessShadowMapViewTest`, `RendererHeadlessTerrainLayersTest`.

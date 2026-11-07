# Adaptive Layout

Read this for any reference with responsive pages, CSS media queries, desktop/mobile variants, or
content-width changes.

## Current capability boundary

`LocalViewportSize` provides the root host viewport in pixels before composition. It is the
Compose-native source for root-level responsive decisions. Use it to select a product layout mode
and compose the appropriate structure.

For a nested region that needs its own adaptive policy, Foundation has `BoxWithConstraints`. It
composes its content during measure with the incoming constraints, so a branch on `maxWidth` has
no frame delay. Prefer passing a deterministic mode from the owning parent when the parent already
knows it.

Foundation has `LazyColumn`, but no window size classes, responsive grid, or lazy grids. Jetpack
Compose's horizontal `LazyRow` has no Awake counterpart either. Do not imitate a missing capability
with a previous-frame `onSizeChanged` value: that creates resize lag and makes composition depend
on a measured child size. Register a Foundation capability gap instead.

## Model responsive intent as modes

Start from the reference's observed structural changes. Define product-level modes only when the
content changes meaningfully, such as the `LandingLayoutMode` below. The product declares it; it is
not a universal engine taxonomy.

```kotlin
enum class LandingLayoutMode { Compact, Standard, Expanded }

val viewport = LocalViewportSize.current
when (landingLayoutMode(viewport)) {
    LandingLayoutMode.Compact -> LandingContentStacked()
    LandingLayoutMode.Standard, LandingLayoutMode.Expanded -> LandingContentSplit()
}
```

Place a single mode decision near the screen or region root. Each branch may use a different
`Row`/`Column` hierarchy, navigation arrangement, content order, or visibility policy. Avoid
scattering `if (viewport.width < ...)` across every child modifier; that creates contradictory
breakpoints and makes the website impossible to tune as one composition.

`LocalViewportSize` is pixels. Store authored product breakpoints in density-independent design
tokens where the product uses them, and make conversion to the host viewport explicit. Do not
compare a raw pixel viewport integer to a value named or assumed to be `Dp`.

## Translate common web adaptations

| Web intent | Awake approach |
|---|---|
| Two-column hero becomes stacked | Compose alternate root branch: `Row` versus `Column`. |
| Desktop navigation becomes a trigger | Switch navigation recipe/structure by layout mode; preserve focus and dismiss behaviour. |
| Page stops widening | Apply a content-width constraint to the enclosing shell; do not scale all children. |
| Card count changes per row | Use an explicit product row/column arrangement for known counts. Register a Foundation grid gap when arbitrary responsive columns are needed. |
| Desktop-only decoration disappears | Remove only decorative content; retain the action or information through the compact structure. |
| Desktop hover affordance | Provide visible, touch, and keyboard-accessible operation in every supported mode. |

Use `weight` only inside `Row`/`Column` and only where the parent is bounded. Do not use
`fillMaxWidth` as a substitute for a responsive structure in an unbounded/wrap-content parent.

## Evidence and verification

For every supported mode, capture its target reference viewport. Add checks immediately below and
above each chosen threshold, and test a long-content case so a visually correct screenshot does
not conceal overflow or clipping. State any inferred threshold as an assumption when the reference
did not expose it.

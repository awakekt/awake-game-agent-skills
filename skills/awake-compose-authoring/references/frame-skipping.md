# Frame skipping, steady-state allocations, and measuring UI cost

## Frame skipping

A host may skip a frame whose inputs did not change (`ComposeHost.skipUnchangedComposition`, and
`skipUnchangedMeasure` on top of it). Both are off by default and whole-frame: one changed read
recomposes or re-measures the whole tree. Write UI that stays correct with them on:

- **Hold what the UI shows in snapshot state** (`mutableStateOf`, a remembered state object, or a
  `PolledState` over a value a store or system owns). A plain field or a getter polled each frame
  changes without the runtime knowing, so a skipped frame keeps showing the old value. Run the
  host's `verifySkippedCompositions` on a screen before turning skipping on for it.
- **Do not compose inside measure for content that animates or only needs viewport size.**
  `BoxWithConstraints` runs subcomposition during measure every frame, so a clock read in there
  invalidates measure every frame and even an idle panel pays subcomposition cost. Use
  `LocalViewportSize.current` with `Box` when you only need viewport bounds; size from placement
  otherwise, and read `LocalFrameClock` in draw, only while something moves.
- **Pace continuous HUD feeds and quantize floats before writing snapshot state.** Because skipping
  is root-wide, a single HUD piece mutating raw unquantized floats at 60–120 Hz (minimap bounds,
  camera heading, roaming entity markers, skill/buff cooldown progress, pulse curves, fade alphas,
  visual touch-stick offsets) defeats skipping for every window and HUD piece on screen:
  - Pace continuous HUD updates (such as minimaps or roaming markers) to ~10 Hz while flushing
    **discrete changes** (open/close, zoom, title, selection, intents, teleports, layout changes)
    on the very next frame with zero lag.
  - Quantize continuous floats to visible visual steps before publishing snapshot state (`coords`,
    `heading`, cooldown/cast/speed fractions, chip trails, fade alpha, visual thumbstick position),
    keeping raw unquantized values only in simulation/input controls.
  - Hoist callback lambdas out of per-frame state objects (fresh `{ ... }` closures inside a `data
    class` fail structural equality every frame), cache derived lists by revision, skip inactive or
    off-theme animations, and guard writes with identity + structural checks before assigning
    `state.value`.
  - Lock active-gameplay skip rate with a deterministic `ComposeHost` test
    (`skipUnchangedComposition = true`, `skipUnchangedMeasure = true`) covering walking, camera
    panning, nearby moving entities, and active cooldowns — asserting most frames skip while
    discrete interactions apply on the very next frame.
- **Never pass a local function reference (`::localFn`) to a non-inlined function in shared/Wasm
  code.** Kotlin/Wasm emits local function-reference reflection metadata embedding the absolute
  source file path into the production `.wasm` binary. Pass a plain lambda `{ ... }` instead.
- **Compare with two runs a side.** Frame cost on one build can settle at two levels between runs.
  A before/after claim needs two agreeing runs of each side on the same commit.

## Steady-state composition and allocation discipline

Keep screen and HUD code declarative and idiomatic—do not trade readability for hand-rolled caches:

- **Never build manual per-widget `*Cache` classes for layout or modifier chains.** Core's
  `remember` (0, 1, 2, or 3 keys), `key`, `CompositionLocalProvider`, `Box`, `Row`, `Column`,
  `FlowRow`, `FlowColumn`, `FlexBox`, and `Modifier.semantics` are `inline` and reuse policies and
  elements on retained nodes. Leaf widgets (`Text`, `Image`, `BasicTextField`, `ShadcnIcon`) reuse
  their internal policy, semantics, and modifier chains through `rememberGroup`. If a Core
  primitive allocates on unchanged inputs, fix it in Awake Core instead of wrapping call sites in
  manual `if (changed)` cache holders.
- **Use the zero-allocation call shapes.**
  - Memoize derived values (styles, formatted labels, stable callbacks) with `remember(k1)`,
    `remember(k1, k2)`, or `remember(k1, k2, k3)`.
  - Use single-value `CompositionLocalProvider(local provides value) { }` when providing one local
    (avoids vararg array allocation), or reuse a remembered `ProvidedLocals` instance via
    `set(local, value)` for a multi-local boundary.
  - Prefer `Box(modifier)` (no trailing block) for empty painted/sized boxes, and hoist constant
    modifiers to a `val` (or `remember` derived chains) so `LayoutNode`'s same-instance fast path
    skips chain rebuilds.
  - Use `Arrangement.spacedBy(...)` / `Arrangement.spacedByHorizontal(...)` (cached `0..32.dp`)
    rather than building custom spacing wrappers.
- **Fix real consumer waste at the data/system layer.** Guard ECS systems and state projections so
  unchanged frames do not allocate fresh state objects or collections (`if (next == prev) return`),
  and hoist static lookup tables and string formatting caches outside `System.update` and
  composables.



# Frame skipping and measuring UI cost

A host may skip a frame whose inputs did not change (`ComposeHost.skipUnchangedComposition`, and
`skipUnchangedMeasure` on top of it). Both are off by default and whole-frame: one changed read
recomposes or re-measures the whole tree. Write UI that stays correct with them on:

- **Hold what the UI shows in snapshot state** (`mutableStateOf`, a remembered state object). A
  plain field or a getter polled each frame changes without the runtime knowing, so a skipped frame
  keeps showing the old value. Run the host's `verifySkippedCompositions` on a screen before
  turning skipping on for it.
- **Do not compose inside measure for content that animates.** `BoxWithConstraints` composes its
  content during measure, so a clock read in there invalidates measure every frame. Size from
  placement, and read `LocalFrameClock` in draw, only while something moves.
- **Compare with two runs a side.** Frame cost on one build can settle at two levels between runs.
  A before/after claim needs two agreeing runs of each side on the same commit.


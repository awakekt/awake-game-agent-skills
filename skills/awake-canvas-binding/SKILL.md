---
name: awake-canvas-binding
description: >
  Choose between the scene canvas and Compose for in-game UI, then build canvas prefabs
  (SceneCanvasElement trees) and bind them at runtime through typed CanvasParts handles, never magic
  string ids. Use before writing in-game UI (nameplate, world bar, HUD panel, window, overlay), a
  binder that writes CanvasElement properties, or a names file of element ids.
license: Apache-2.0
metadata:
  author: awake
  last-updated: '2026-11-07'
  keywords: Awake, canvas, Compose, canvas or Compose, canvasPrefab, CanvasParts, CanvasWidgetParts, SceneCanvasElement, CanvasElement, nameplate, HUD widget, typed handle, magic string
---

# Awake Canvas Binding

Use this skill when you build a canvas prefab and later change its elements from code: HUD bars,
unit frames, windows, chat, overlays. It covers how code refers to the prefab's parts. For the
state that drives them, read [awake-state-management](../awake-state-management/SKILL.md) (HUD
section) first; for sizing and spacing, [awake-ui-layout-guidance](../awake-ui-layout-guidance/SKILL.md).

## Canvas or Compose?

Decide by where the UI lives and what drives it, not by habit:

| UI | Use | Why |
|---|---|---|
| Anchored to the world: nameplates, health bars over entities, floating damage text, target markers | **Canvas** | Elements are ECS entities: they follow entities, sort with the scene, bind to components (`CanvasBinding`), and stay cheap at hundreds of copies |
| Laid out and themed by designers, saved with a scene, overridden from data | **Canvas** | A prefab is a `ScenePrefab` an editor opens and saves back unchanged |
| Screen-space and driven by game state: windows, dialogs, party frames, skill bar, buffs, target frame, chat, quest tracker | **Compose** (`:awake:compose`) | UI is a function of state; lists and conditionals follow the state with no update code. See [awake-compose-authoring](../awake-compose-authoring/SKILL.md) |
| Menus, editors, launchers, tools around the game | **Compose** | Application UI |

- The two run in one Compose host: `SceneCanvas(world)` is a composable, so Compose UI declared after
  it draws on top and shares state, drag and drop, and tooltips with it.
- Don't keep a hidden canvas copy of a window that moved to Compose. Every canvas element costs a
  little every frame, visible or not, and systems that keep copies hidden scan all of them.
- Don't park a whole HUD theme as an invisible subtree. Build what is shown; drop what isn't.
- A canvas control's custom slot (`slotContent`) can draw a composable inside a control the editor
  placed. It is wired by name, so prefer Compose for screen UI written in code.
- Declarative canvas content, with Compose nested inside canvas elements, is planned in
  [awakekt/awake#1391](https://github.com/awakekt/awake/issues/1391). Don't write against it until it
  ships.

## The anti-pattern: magic string ids

```kotlin
// Build
part(Names.slotPart(id, i, Names.ICON), CanvasElementKind.Image) { size(32.dp, 32.dp) }
// Bind, somewhere else, every frame
elements.element(Names.slotPart(id, i, Names.ICON))?.image = slot.icon
```

What's wrong with it:
- **Silent failure:** a typo or renamed part compiles, the lookup returns null, and `?.` skips the
  write, so a slot that never updates is the only symptom.
- **No single source of truth:** each id lives in the builder, the binder and a names file, kept in
  sync by convention, so a rename means shotgun edits.
- **Untyped parts:** any property can be written to any kind (`fraction` on a text element).
- **Hidden coupling and cost:** the binder depends on the prefab's exact shape through a string
  lookup, and rebuilds those strings on every frame.

This is the same mistake as `transform.Find("Panel/Slot3/Icon")` in Unity or `findViewById` with
tags on Android. Those ecosystems moved to serialized references, ViewBinding and Compose.

## The pattern: declare parts once, typed

1. **Declare** each widget's parts once. Ids are derived from the structure, never typed twice.
2. **Build** the prefab from those handles. The saved prefab still holds plain string ids, so it
   stays data.
3. **Resolve** the handles once against the instantiated root, and fail fast on a missing part.
4. **Bind** from a state object, writing through typed views and skipping unchanged values.

Core's `CanvasParts` (`awake:scene:canvas`) is this pattern. A `CanvasWidgetParts` is the widget;
each kind's function (`text`, `image`, `bar`, `sweep`, `button`, `panel`, `view`) declares a typed
part, `group` and `list` nest them, and ids are composed from the declaration (`bar.slot-3.icon`):

```kotlin
// 1. Declare: one place owns the ids
class SlotParts(scope: CanvasPartScope) : CanvasParts(scope) {
    val button = button()            // "bar.slot-3"
    val icon = image("icon")         // "bar.slot-3.icon"
    val cooldown = sweep("cooldown")
    val count = text("count")
}
class ActionBarParts(slotCount: Int) : CanvasWidgetParts("bar") {
    val frame = panel()
    val slots = list("slot", slotCount) { SlotParts(it) }
}

// 2. Build from the handles
fun actionBar(parts: ActionBarParts) = canvasPrefab(guid = BAR_GUID, name = "Action Bar", root = parts.frame) {
    for (slot in parts.slots) button(slot.button) {
        image(slot.icon) { size(32.dp, 32.dp) }
        sweep(slot.cooldown) { }
        text(slot.count) { fontSize = 10.sp }
    }
}

// 3. Resolve once when placed: throws CanvasPartResolutionException naming each missing part
val bar = ActionBarParts(slotCount = 10).resolve(world, root)

// 4. Bind from state: typed fields on cached elements, no lookups, no strings
fun bind(state: BarState) {
    for (i in bar.slots.indices) {
        val s = state.slots[i]
        if (bar.slots[i].icon.image != s.icon) bar.slots[i].icon.image = s.icon
        bar.slots[i].cooldown.value = s.cooldown
    }
}
```

A part whose shipped prefab already saves another id keeps it with `pinnedId`. See "Bind elements
with typed handles" in Core's `website/docs/guides/game-ui.md`.

## Rules

- **One owner per id.** Only the parts declaration composes ids. Builders and binders take handles,
  never strings or a names helper.
- **Resolve at bind time, not per frame.** Cache resolved elements. Never call
  `findCanvasElement` or `element(id)` inside `System.update` or a per-frame `bind`.
- **Missing parts are errors.** Throw with the id (or fail the widget's test). Never `?.`-skip.
- **Bind from state, diff the writes.** A steady state should write nothing and allocate nothing.
  No string building, `toString()` on unchanged numbers, or new lists per frame.
- **Saved ids are data contracts.** Once a prefab ships, editors, themes, saved layouts and game
  overrides depend on its ids. Derive new ids the same way, and pin existing ones in a test when
  you migrate (`assertEquals(listOf("bar.slot-0.icon", …), prefabIds(barPrefab(…)))`).
- **Expose widget ids, not part ids.** A public names object lists top-level widget ids that games
  use to find or override a widget. Part names stay internal to the parts declaration.
- **Keep views passive.** The binder maps state to elements and input to intents. Game rules stay
  in the Store (see [awake-state-management](../awake-state-management/SKILL.md)).

## Review checklist

Flag these in a review:
- [ ] String-concatenated element ids outside a parts declaration (`"$id.slot-$i.icon"`,
      `Names.part(id, …)` in a binder).
- [ ] `findCanvasElement`, `element(id)` or a map lookup by id inside per-frame code.
- [ ] `?.` after an element lookup with no error path.
- [ ] The same id literal in more than one file.
- [ ] Properties written to an element kind that doesn't use them.
- [ ] A binder that writes every field every frame regardless of change.
- [ ] A migration that changes saved ids without a test pinning the old ones.

## Verification

- A unit test resolves every part of a built prefab, so a missing or renamed part fails at test time.
- A test pins the prefab's ids when they're already shipped.
- A steady-state bind test asserts no writes (and no allocations, where an allocation probe exists).
- Screenshot tests (see [awake-ui-design-audit](../awake-ui-design-audit/SKILL.md)) still cover the look.

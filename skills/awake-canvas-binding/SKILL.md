---
name: awake-canvas-binding
description: >
  Build Awake canvas prefabs (SceneCanvasElement trees) and update them at runtime without magic
  string ids. Use before writing a reusable in-game widget (HUD bar, unit frame, window, overlay),
  a binder that writes CanvasElement properties, or a names file of element ids; it keeps prefabs as
  data while making parts typed, declared once, resolved once and bound from state.
license: Apache-2.0
metadata:
  author: awake
  last-updated: '2026-10-26'
  keywords: Awake, canvas, canvasPrefab, SceneCanvasElement, CanvasElement, findCanvasElement, element id, binder, HUD widget, typed handle, magic string
---

# Awake Canvas Binding

Use this skill when you build a canvas prefab and later change its elements from code: HUD bars,
unit frames, windows, chat, overlays. It covers how code refers to the prefab's parts. For the
state that drives them, read [awake-state-management](../awake-state-management/SKILL.md) (HUD
section) first; for sizing and spacing, [awake-ui-layout-guidance](../awake-ui-layout-guidance/SKILL.md).

## Canvas prefab or Compose?

- **Canvas prefab** (`canvasPrefab { … }` producing `SceneCanvasElement` nodes): in-game UI that
  must be **data**: saved with the scene, editable in an editor, themed from data, overridden by a
  game without Kotlin, and cheap to update every frame (bars, cooldowns, floating numbers).
- **Compose** (`:awake:compose`): application and tool UI around the game (menus, editors, launchers).
  See [awake-compose-authoring](../awake-compose-authoring/SKILL.md).

Don't port a canvas widget to Compose to fix naming problems. Fix how code names its parts.

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

Core is adding this to `scene:canvas` ([awakekt/awake#1082](https://github.com/awakekt/awake/issues/1082)).
Until it ships, keep the same shape locally so you can move to Core's types with no redesign (property names below are the shape, not exact API; check `CanvasElement` before writing):

```kotlin
// 1. Declare: one place owns the ids ("bar.slot-3.icon")
class SlotParts(val id: String) {
    val icon = "$id.icon"
    val cooldown = "$id.cooldown"
    val count = "$id.count"
}
class BarParts(val id: String, slots: Int) {
    val slots = List(slots) { SlotParts("$id.slot-$it") }
}

// 2. Build from the handles
fun barPrefab(theme: Theme, parts: BarParts) = canvasPrefab(guid = stableGuid(parts.id), name = parts.id, id = parts.id) {
    for (slot in parts.slots) part(slot.id, CanvasElementKind.Panel) {
        part(slot.icon, CanvasElementKind.Image) { size(theme.slot, theme.slot) }
        part(slot.cooldown, CanvasElementKind.Panel) { /* meter look */ }
        part(slot.count, CanvasElementKind.Text) { fontSize = theme.small }
    }
}

// 3. Resolve once and fail fast; 4. bind from state
class BarView(world: World, root: Entity, parts: BarParts) {
    private class Slot(val icon: CanvasElement, val cooldown: CanvasElement, val count: CanvasElement)
    private val slots = parts.slots.map { s ->
        fun need(id: String) = world.findCanvasElement(root, id)?.let { world.get<CanvasElement>(it) }
            ?: error("Canvas part missing: $id")
        Slot(need(s.icon), need(s.cooldown), need(s.count))
    }
    private var last: BarState? = null

    fun bind(state: BarState) {
        if (state == last) return
        state.slots.forEachIndexed { i, s ->
            val view = slots[i]
            if (view.icon.image != s.icon) view.icon.image = s.icon
            view.count.text = s.count?.toString().orEmpty()
        }
        last = state
    }
}
```

With Core's API, the `SlotParts` strings become `CanvasPart<K>` handles (typed per element kind),
and `need(...)` becomes `parts.resolve(world, root)`. The structure stays the same.

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

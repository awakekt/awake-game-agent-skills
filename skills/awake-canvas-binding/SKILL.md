---
name: awake-canvas-binding
description: >
  Choose between canvas content, a canvas prefab and Compose for in-game UI. Declare state-driven
  canvas UI with canvasContent (keyed elements recomposed from a StateFlow or Store), place and bind
  authored prefabs from it, nest Compose UI in an element with compose { }, and bind prefabs through
  typed CanvasParts handles, never magic string ids. Use before writing in-game UI (nameplate, world
  bar, HUD panel, party frame, window, overlay), a binder that writes CanvasElement properties, or a
  names file of element ids.
license: Apache-2.0
metadata:
  author: awake
  last-updated: '2026-11-07'
  keywords: Awake, canvas, Compose, canvas or Compose, canvasContent, CanvasContent, CanvasEntityApplier, CanvasContentSystem, declarative canvas, canvas content, prefab placement, nested compose, canvasPrefab, CanvasParts, CanvasWidgetParts, SceneCanvasElement, CanvasElement, nameplate, HUD widget, typed handle, magic string
---

# Awake Canvas Binding

Use this skill when code drives in-game canvas UI: HUD bars, unit frames, party frames, overlays,
nameplates. Declare state-driven canvas UI with `canvasContent`. Bind an authored prefab through
typed `CanvasParts` handles. For the state that drives them, read
[awake-state-management](../awake-state-management/SKILL.md) (HUD section) first; for sizing and
spacing, [awake-ui-layout-guidance](../awake-ui-layout-guidance/SKILL.md).

## Canvas content, a prefab, or Compose?

Decide by where the UI lives and what drives it, not by habit:

| UI | Use | Why |
|---|---|---|
| HUD whose elements follow game state: party frames, buff row, skill bar, target frame, quest tracker | **Canvas content** (`canvasContent`) | Elements are declared from state; `if`, `forEach` and `key` add, remove and reorder them with no update code. They stay canvas entities |
| Anchored to the world: nameplates, health bars over entities, floating damage text, target markers | **Canvas** (content or prefab) | Elements follow entities, sort with the scene, bind to components (`CanvasBinding`), and stay cheap at hundreds of copies |
| Laid out and themed in an editor, saved with a scene, overridden from data | **Canvas prefab** (`canvasPrefab`, `CanvasParts`) | A prefab is a `ScenePrefab` an editor opens and saves back unchanged. Canvas content can place and bind it |
| Windows and dialogs with text input, scrolling or focus; chat; menus, launchers, tools | **Compose window** (`:awake:compose`) | Application UI with Compose behaviour. See [awake-compose-authoring](../awake-compose-authoring/SKILL.md) |
| One part of a canvas element the canvas can't draw, such as a scrolling list or a text field | **Nested `compose { }`** in that element's content | The UI keeps the element's place in canvas order, its alpha and its follow position |

- Canvas and Compose run in one Compose host: `SceneCanvas(world)` is a composable, so Compose UI
  declared after it draws on top and shares state, drag and drop, and tooltips with it.
- Don't keep a hidden canvas copy of a window that moved to Compose. Every canvas element costs a
  little every frame, visible or not, and systems that keep copies hidden scan all of them.
- Don't park a whole HUD theme as an invisible subtree. Build what is shown; with canvas content,
  an `if` does it.
- A control's custom slot (`slotContent`) stays for prefabs authored in an editor. Code uses
  `compose { }`.

## Declare canvas content from state (the default)

`canvasContent(world, root, state) { s -> … }` builds canvas elements under `root` as a function of
a `StateFlow` or a `Store`. It runs on the `:awake:compose:runtime` runtime through a
`CanvasEntityApplier`, so `key`, `remember` and composition locals work as in Compose. The element
functions are `panel`, `text`, `image`, `bar`, `button`, and `element(kind, …)` for any other kind.
Their settings are `CanvasElementScope`, the same as `canvasPrefab`'s builder. A leaf's block is
its settings. A panel takes `settings = { … }`, and its block declares its children. This follows
Core's unit frame sample (`CanvasUnitFrameSample.kt`):

```kotlin
data class PartyMember(val id: String, val name: String, val hp: Int, val maxHp: Int)
data class PartyState(val members: List<PartyMember>, val inCombat: Boolean = false)

context(_: Composer)
fun unitFrame(member: PartyMember) {
    panel(id = "frame-${member.id}", settings = {
        size(220.dp, 44.dp)
        layout = CanvasLayout(direction = CanvasDirection.Column, gap = 4f, padding = 8f)
    }) {
        text(id = "name-${member.id}") { size(204.dp, 16.dp); text = member.name; fontSize = 12.sp }
        bar(id = "hp-${member.id}") {
            size(204.dp, 12.dp)
            value = (member.hp.toFloat() / member.maxHp.coerceAtLeast(1)).coerceIn(0f, 1f)
            color = Color(0.8f, 0.15f, 0.15f, 1f)
        }
    }
}

fun partyHud(world: World, hudRoot: Entity, party: StateFlow<PartyState>): CanvasContent =
    canvasContent(world, root = hudRoot, state = party) { state ->
        panel(id = "party", settings = {
            anchor = CanvasAnchor.TopLeft
            size(220.dp, 600.dp)
            layout = CanvasLayout(direction = CanvasDirection.Column, gap = 6f)
        }) {
            state.members.forEach { member -> key(member.id) { unitFrame(member) } }
            if (state.inCombat) text(id = "combat") { textKey = "hud.combat" }
        }
    }
```

- **When it runs.** `CanvasContentSystem` reruns the block on a frame where its state holds a new
  value, and on no other frame. The scene runtime's infrastructure systems include it. A host that
  runs its own systems adds it ahead of `TransformSystem`.
- **New value, new object.** The system compares references. Emit a new immutable state; mutating a
  list in place and emitting it again changes nothing.
- **No read tracking yet.** It reruns when its `StateFlow` emits, or when the host calls
  `CanvasContent.recompose()`. It does not rerun on `State` reads: `collectAsState()` in
  `:awake:compose:state` is for Compose UI. For state that is neither a flow nor a store, use
  `canvasContent(world, root) { … }` and call `recompose()` when it changes.
- **What it writes.** A pass writes only the settings that changed. A pass that declares what the
  last one did writes nothing. `CanvasContent.applier` counts `writes`, `created` and `destroyed`.
- **Keys.** Wrap each list item in `key(item.id)`. A keyed item that moves keeps its entities; one
  that goes is destroyed with everything under it.
- **Disposing.** `dispose()` destroys what the block made and leaves `root`.

## Place and bind a prefab from canvas content

An authored prefab stays the format an editor opens and saves. Canvas content places a copy where
its state says, and binds it through its `CanvasParts` declaration:

```kotlin
class UnitFrameParts : CanvasWidgetParts("frame") {
    val frame = panel()
    val name = text("name")
    val health = bar("health")
}
// unitFramePrefab: a ScenePrefab built from UnitFrameParts with canvasPrefab, as in step 2 below.

canvasContent(world, root = hudRoot, state = party) { state ->
    panel(id = "party", settings = { layout = CanvasLayout(direction = CanvasDirection.Column, gap = 6f) }) {
        state.members.forEach { member ->
            key(member.id) {
                prefab(unitFramePrefab, parts = { UnitFrameParts() }) {
                    name.text = member.name
                    health.value = member.hp.toFloat() / member.maxHp.coerceAtLeast(1)
                }
            }
        }
    }
}
```

The copy is made once per place or `key`, and destroyed with it. Its parts are resolved once per
copy; the bind block writes through them on each pass. `prefab(unitFramePrefab)` places a copy with
nothing to bind. A prefab node with a non-canvas component throws. A prefab placed outside canvas
content is resolved and bound by hand, as below.

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

- **Declare from state; don't hand-bind what canvas content can declare.** A per-frame binder that
  shows, hides or rebuilds elements as a list changes is canvas content written by hand.
- **Canvas content owns its elements.** Change the state, never an element the block made: the block
  writes a setting only when its own declaration of it changes, so an outside write goes stale.
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
- [ ] A list in canvas content without `key(item.id)`, or code writing an element the block made.

## Verification

- A unit test resolves every part of a built prefab, so a missing or renamed part fails at test time.
- A test pins the prefab's ids when they're already shipped.
- A steady-state bind test asserts no writes (and no allocations, where an allocation probe exists).
  For canvas content, assert on `CanvasContent.applier`'s `writes` and `created` across frames with
  `CanvasContentSystem`, as `CanvasUnitFrameSampleTest` does.
- Screenshot tests (see [awake-ui-design-audit](../awake-ui-design-audit/SKILL.md)) still cover the look.

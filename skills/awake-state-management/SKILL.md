---
name: awake-state-management
description: >
  Manage Awake application, editor, sample, and in-game HUD state with a thin Store/Contract, MVI,
  or UDF shape. Use before adding state, intents, effects, reducers, StateFlow, HUD windows, or
  effect draining outside ECS. It keeps frame-loop effects synchronous and separates simulation,
  document, session, HUD window, and widget state.
license: Apache-2.0
metadata:
  author: awake
  last-updated: '2026-09-17'
  keywords: Awake state, MVI, Store, Contract, Intent, Effect, StateFlow, reducer, effect draining, editor state, game HUD, window state
---

# Awake State Management

This skill governs application, editor, sample, and in-game HUD state. It does not replace ECS
state or turn engine modules into app architecture. Read [the app-composition skill](../awake-app-composition/SKILL.md)
for lifecycle ownership and [the Compose-authoring skill](../awake-compose-authoring/SKILL.md) when
retained Compose renders the state.

## Choose the smallest state shape

| Need | Use |
|---|---|
| Simulation that ticks, collides, renders, or replicates | ECS components and systems |
| Authored scene/provider configuration that must save | `SceneDocument` and versioned provider payload |
| Entity authoring tool state (brush size, dynamics, layers, companion asset paths) | Ephemeral ECS capability component on the entity (`*BrushComponent`, `*AssetReference`) |
| In-game HUD window or feature state (inventory, taskbar, party, quest, dialog, chat) | Cohesive per-feature Store/Contract (`*Contract` / `*Store`) synced at a single frame boundary |
| Session/editor mode, selection, panel layout, async progress, or user action state | Explicit Store/Contract or a thin state holder |
| A shared UI value with no asynchronous work (active tab, picker visibility) | Hoist to the lowest shared UI owner; use explicit state/events |
| A private transient widget detail | `remember` in the retained node |

Do not put entities, renderer objects, a `World`, or mutable provider resources in Store state. Store
stable IDs, immutable display data, and operation state; the effect handler or session resolves the
live engine object when it executes. Never store canonical entity tool parameters or asset links in
Store or UI state holders—they belong on the entity's ECS components.

Use full MVI only when a coherent feature has state transitions plus user actions and/or one-shot
effects. A simple static surface or local toggle does not need a Contract. Keep one Contract per
cohesive feature, not one repository-wide god store.

## Store/Contract boundary

The standard shape is immutable State, sealed Intent, and sealed Effect:

```kotlin
object EditorContract {
    data class State(
        val mode: Mode = Mode.Edit,
        val selectedEntityId: Int? = null,
        val save: SaveState = SaveState.Idle,
    )

    sealed interface Intent {
        data class SelectEntity(val id: Int?) : Intent
        data object SaveRequested : Intent
    }

    sealed interface Effect {
        data object SaveDocument : Effect
    }
}
```

`dispatch(intent)` is the sole mutation entry point. It updates `State` atomically and queues an
Effect when work must leave the reducer. Reducers do not write files, mutate the World, load
assets, call the renderer, or start an uncontrolled coroutine.

`StateFlow` plus a buffered `Channel<Effect>` is the established sample implementation. Flow and
coroutines are allowed outside the frame loop; a retained Compose tree does not collect them.
During a frame it reads the current state snapshot and dispatches intents through explicit
callbacks. The application/session owner drains effects synchronously once per frame:

```kotlin
store.drainEffects().forEach { effect ->
    when (effect) {
        EditorContract.Effect.SaveDocument -> sceneWriter.save(session.document)
    }
}
```

An asynchronous effect handler starts work outside the frame thread and dispatches a result intent
when it completes. Do not make a later Compose pass responsible for collecting, replaying, or
acknowledging that effect.

## In-game HUD and gameplay windows (ECS ↔ Store ↔ View)

Game HUDs (inventory, taskbar, skill tree, quest log, party, guild, chat, NPC dialog) follow the
exact same Store/Contract separation whether rendered via retained Compose (`:awake:compose`) or
`SceneCanvasElement` nodes:

1. **Never create a "kitchen-sink" `PlayerState` ECS component.** Dumping open window sets, hover
   tooltips, chat logs, party/trade/guild views, taskbar shortcuts, and outgoing UI request lists
   into one mutable component on the player entity couples every window to every gameplay system.
2. **Never write 500+ line imperative `WindowSystem : System` classes** that mix AABB pointer
   hit-testing (`contains(mouse)`), business rules, domain mutation, and direct `CanvasElement` /
   `CanvasText` node mutation inside `update(world, delta)`.
3. **Split each HUD feature into three focused parts**:
   - **Contract & Store (`TaskbarContract` / `TaskbarStore`)**: Pure immutable `State`, sealed
     `Intent` (`WorldSynced`, `SlotActivated`, `ShortcutAssigned`, `SubTabSelected`), and sealed
     `Effect` (`UseInventorySlot`, `CastSkill`, `PlayUiSound`). Unit-tested on plain JVM with zero
     ECS or renderer setup.
   - **Pure View / Presenter**: Reads `State` to render Compose widgets or update `CanvasElement`
     properties, and maps pointer/keyboard input into `store.dispatch(Intent)`. Zero domain or
     network mutation inside the view.
   - **Thin ECS Bridge (`HudSyncSystem`)**: At the start of the HUD frame phase, projects ECS data
     (`Health`, `Inventory`, `SkillBook`) into `store.dispatch(Intent.WorldSynced(...))`. At the
     end of the phase, drains `store.drainEffects()` into focused ECS command components or network
     packets.

```kotlin
object TaskbarContract {
    data class State(
        val hpRatio: Float = 1f,
        val activePage: Int = 0,
        val slots: List<ShortcutSlotUi> = emptyList(),
    )

    sealed interface Intent {
        data class WorldSynced(val hpRatio: Float, val slots: List<ShortcutSlotUi>) : Intent
        data class ActivateSlot(val index: Int) : Intent
        data class SelectPage(val page: Int) : Intent
    }

    sealed interface Effect {
        data class ExecuteShortcut(val slotId: String) : Effect
        data object PlayClickSound : Effect
    }
}
```

## Frame and lifecycle rules

- Drain queued effects at one named application/session boundary, once per frame. An effect is
  consumed at most once; a second drain is empty.
- Effects that mutate scene state run through the session's ownership boundary, not from a panel.
- Starting Play creates an isolated world from authored data. Stopping Play destroys it. Store state
  can request the transition, but simulation output never writes authored data back implicitly.
- UI events dispatch intents. UI rendering reads state; it does not directly mutate the World or
  provider resources.
- Retained Compose has no snapshot invalidation. `StateFlow.value` is read during each frame; a
  host adapter may provide the Store/state through `CompositionLocalProvider`, but that does not
  transfer construction, disposal, or effect ownership to the UI.

## Required tests

- A reducer test for every meaningful intent and state transition.
- Effects are asserted separately from state and drain exactly once.
- A lifecycle test proves the effect handler is called in the intended frame/session phase.
- Edit/Play tests prove isolated Play mutations cannot change authored data without an explicit
  Apply action.
- Async completion tests dispatch a result intent and do not rely on a Compose collector.

## Before finishing

- State is in the correct layer: ECS, document, Store/session, hoisted UI, or local `remember`.
- State holds immutable data and stable IDs, not engine resources or live ECS objects.
- In-game HUD windows use cohesive per-feature Contracts/Stores—not a monolithic `PlayerState`
  component or imperative `System` loops that mix hit-testing, business rules, and node mutation.
- Intent handling is the only Store mutation path; reducers have no engine or IO side effects.
- Effects are queued, drained synchronously once, and tested as one-shot work.
- A retained Compose consumer pulls a state snapshot and dispatches intents; it does not use
  AndroidX `ViewModel`, `LaunchedEffect`, snapshot state, or Flow collection inside the UI engine.

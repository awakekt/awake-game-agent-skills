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
  last-updated: '2026-11-23'
  keywords: Awake state, MVI, Store, Contract, Intent, Effect, EffectSource, EffectDrainer, ContextualEffectDrainer, SceneBridge, SceneBridgeHandle, drainEffects, StateFlow, reducer, effect draining, editor state, overlay state, ViewModel, window state
---

# Awake State Management

This skill governs application, editor, sample, and scene overlay state. It does not replace ECS
state or turn engine modules into app architecture. Read [the app-composition skill](../awake-app-composition/SKILL.md)
for lifecycle ownership, [the Compose-authoring skill](../awake-compose-authoring/SKILL.md) when
retained Compose renders the state, and [scene-bridge-and-dispatchers.md](references/scene-bridge-and-dispatchers.md)
for the complete declarative 4-way State/UI/Behavior/`SceneBridge` template (scene-scoped ViewModel
pattern), naming rules, and `childStoreScope` / `ioDispatcher` guidance.

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

`StateFlow` plus a buffered `Channel<Effect>` is provided out of the box by `:awake:core:state`
(`reducerStore` / `DefaultReducerStore` for pure reducers, `MutableEffectStore` for custom domain
methods — never hand-roll a duplicate `MutableStateFlow` + `Channel<Effect>` store). Flow and
coroutines are allowed outside the frame loop; a retained Compose tree does not collect them.
During a frame it reads the current state snapshot and dispatches intents through explicit
callbacks. The application/session owner drains effects synchronously once per frame using the
zero-allocation callback overload `drainEffects(action)` (or `EffectDrainer` across multiple
`EffectSource` stores so idle frames allocate nothing):

```kotlin
// Single store — zero-allocation per-frame drain (prefer over drainEffects().forEach { ... }):
store.drainEffects { effect ->
    when (effect) {
        EditorContract.Effect.SaveDocument -> sceneWriter.save(session.document)
    }
}

// Multiple scene stores coordinated at the session frame boundary via SceneBridge + ContextualEffectDrainer:
val drainer = ContextualEffectDrainer<FrameContext>()
drainer.bind(
    store = store,
    closeWithDrainer = true,
    sync = { ctx, state -> syncIntoStore(ctx, state) },
    onEffect = { ctx, effect -> handleEffect(ctx, effect) },
)
// Pair directly with declarative Compose UI (acts like a scene-scoped ViewModel):
//   ui(bridge = { SceneUiModel(session.coroutineScope) }) { model -> SceneOverlay(model) }
// Or keep the SceneBridgeHandle<T> for lifecycle hooks / tests too:
//   val model = bridge { SceneUiModel(session.coroutineScope) }
//   ui(model) { active -> SceneOverlay(active) }
// Frame order inside SceneSession:
//   beforeAdvance(world, delta) -> drainer.drainEffects(ctx)  // 0-frame click latency into ECS
//   afterAdvance(world, delta)  -> drainer.sync(ctx)          // fresh ECS state before Compose draws
//   close()                     -> drainer.close()            // closes every owned store automatically
```

An asynchronous effect handler starts work outside the frame thread and dispatches a result intent
when it completes. Do not make a later Compose pass responsible for collecting, replaying, or
acknowledging that effect.

## In-game HUD and gameplay windows (ECS ↔ Store ↔ View)

Game HUDs (inventory, taskbar, skill tree, quest log, party, guild, chat, NPC dialog) follow the
exact same Store/Contract separation whether rendered via retained Compose (`:awake:compose`) or
`SceneCanvasElement` nodes. Which one a piece uses is decided by the split in `awake-canvas-binding`:
world-anchored and editor-authored UI on the canvas, screen-space UI driven by state on Compose.

1. **Never create a "kitchen-sink" player-state ECS component.** Dumping open window sets, hover
   tooltips, chat logs, party/trade/guild views, taskbar shortcuts, and outgoing UI request lists
   into one mutable component on the player entity couples every window to every gameplay system.
2. **Never put Compose UI, Compose state, or window/HUD registries inside an ECS `System`.**
   - Do **not** import `com.awakekt.awake.compose.*` inside any ECS `System` class or file.
   - Do **not** use singleton ECS components on `World` as a Compose lambda registry (`world.registerWindow { ... }`) or write one `WindowSystem : System, AutoCloseable` per HUD panel (it leaks `AutoCloseable` stores, runs redundant per-frame `localPlayer()` lookups, and drags UI into `SceneSchedule`).
   - Do **not** write 500+ line imperative `WindowSystem : System` classes mixing hit-testing, business rules, and direct `CanvasElement` mutation inside `update(world, delta)`.
3. **Split each HUD feature into three focused parts**:
   - **Contract & Store (`TaskbarContract` below, held in a `ReducerStore` from `:awake:core:state`)**:
     Pure immutable `State`, sealed `Intent` (`WorldSynced`, `ActivateSlot`, `SelectPage`), and
     sealed `Effect` (`ExecuteShortcut`, `PlayClickSound`). Unit-tested on plain JVM with zero ECS
     or renderer setup.
   - **Pure View / Presenter**: Reads `State` to render Compose widgets or update `CanvasElement`
     properties, and maps pointer/keyboard input into `store.dispatch(Intent)`. Zero domain or
     network mutation inside the view. For canvas views, refer to parts through typed handles
     declared once and resolved once, never string ids: see `awake-canvas-binding`.
   - **Session-level `SceneBridge` + `ContextualEffectDrainer<C>` (scene-scoped ViewModel)**: Mounted
     declaratively at the Compose host boundary via `ui(bridge = { ... }) { model -> ... }` or
     `val handle = bridge { ... }; ui(handle) { model -> ... }` — **not** as an ECS `System`.
     `beforeAdvance` calls `drainer.drainEffects(ctx)` so UI clicks reach simulation on the same
     frame; `afterAdvance` calls `drainer.sync(ctx)` so Compose renders fresh ECS state; `close()`
     disposes every owned store automatically (`closeWithDrainer = true`). Read loaded tables/assets
     from `LoadedProject.content` instead of wrapping UI in `SceneFeature.plan`. Name bridges and
     screens after their actual domain or overlay (for example *PlayOverlayModel* or *EmotePanel*),
     avoiding vague `Game*` or `Hud*` boilerplate prefixes.

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

// Scene-scoped ViewModel implementing SceneBridge; ReducerStore & ContextualEffectDrainer are Core.
// Pair directly with declarative Compose UI via `ui(bridge = { ... }) { model -> ... }`.
class PlayOverlayModel(parentScope: CoroutineScope) : SceneBridge {
    private val drainer = ContextualEffectDrainer<World>()
    val taskbar = taskbarStore(scope = parentScope.childStoreScope())

    init {
        drainer.bind(
            store = taskbar,
            closeWithDrainer = true,
            sync = { world, state -> syncTaskbar(world, state, taskbar::dispatch) },
            onEffect = { world, effect -> handleTaskbarEffect(world, effect) },
        )
    }

    override fun beforeAdvance(world: World, delta: Float) = drainer.drainEffects(world)
    override fun afterAdvance(world: World, delta: Float) = drainer.sync(world)
    override fun close() = drainer.close()
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
- Retained Compose recomposes every frame by default, so `StateFlow.value` is read during each
  frame. A host that opts into skipping unchanged frames only sees snapshot state: mirror a value
  the UI shows into `mutableStateOf` at the boundary rather than polling a plain field (see
  `awake-compose-authoring`, "State a skipped frame can see"). A host adapter may provide the Store/state through `CompositionLocalProvider`, but that does not
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
- In-game HUD windows use cohesive per-feature Contracts/Stores—not a monolithic player-state
  component or imperative `System` loops that mix hit-testing, business rules, and node mutation.
- Intent handling is the only Store mutation path; reducers have no engine or IO side effects.
- Effects are queued, drained synchronously once, and tested as one-shot work.
- A retained Compose consumer pulls a state snapshot and dispatches intents; it does not use
  AndroidX `ViewModel`, `LaunchedEffect`, snapshot state, or Flow collection inside the UI engine.

# Declarative State, UI, Behavior Separation (`SceneBridge` as ViewModel) and Dispatchers

Reference for `awake-state-management`. Follow this 4-layer separation and dispatcher table whenever
you add declarative Compose UI (overlays, panels, editors, or play screens) over an Awake ECS
`SceneSession`.

## Mental model: `SceneBridge` is Awake's scene-scoped ViewModel

| Android / generic Compose | Awake scene runtime |
|---|---|
| `ViewModel` scoped to a screen / route | `SceneBridge` paired with `ui(bridge = { ... }) { model -> ... }` or `SceneBridgeHandle<T>` |
| `viewModelScope` | `session.coroutineScope.childStoreScope()` (cancelled automatically when the bridge or scene closes) |
| `StateFlow` UI state collected in Compose | `ReducerStore` / `MutableStateFlow` exposed on the bridge and read with `collectAsState()` |
| Repository / UseCase calls from intents | `beforeAdvance` drains queued `Effect`s into ECS request components (0-frame lag); async work uses `ioDispatcher` |
| Domain stream mapped to UI state | `afterAdvance` projects fresh ECS state into stores right before Compose builds the frame |

- **No AndroidX `ViewModel`, no `Dispatchers.Main` frame hops, no `World` UI registries**: new
  declarative scenes pass the bridge instance straight into Compose (`ui(bridge = { ... }) { model -> ... }`)
  and render visibility with plain `if` / `?.let` instead of mutating a `World` window map.
- **Keep names domain-specific, not hardcoded to "Game" or "Hud"**: name bridges, contexts, and
  screens after what they actually present (for example *SceneUiModel*, *PlayOverlaySession*,
  *EmotePanel*, *FrameContext*, *EditorOverlayModel*) rather than prefixing everything with
  `Game*`, `InGame*`, or `Hud*`.

## Dispatcher strategy across Desktop, Android, iOS, and WasmJs

| Work | Dispatcher / Thread | Rule |
|---|---|---|
| ECS `System.update`, `SceneBridge` (`beforeAdvance` / `afterAdvance`), `ContextualEffectDrainer`, `ReducerStore.dispatch`, Compose frame | **Synchronous on the engine frame thread** | Never use `Dispatchers.Main` for engine/UI frames (on Desktop JVM `Dispatchers.Main` can bind to Swing/AWT EDT instead of the GLFW/Vulkan/WebGPU render thread). `dispatch()` uses atomic `MutableStateFlow.update` + non-suspending `trySend()`; `drainEffects()` uses `tryReceive()`. Zero coroutine launches and zero thread hops per frame. |
| Async CPU work (prewarms, glTF decode, background store work) | **`SceneSession.coroutineScope`** (`Dispatchers.Default`, child of `AppCoroutineScope`) | Derive every store's scope via `session.coroutineScope.childStoreScope()` so uncaught exceptions reach `AppErrorHandler` and session teardown cancels every child store automatically. Closing one store cancels only its own child `SupervisorJob`. |
| Blocking disk, asset, or network I/O | **Awake's `ioDispatcher`** (`com.awakekt.awake.core.io.ioDispatcher`) | Maps to `Dispatchers.IO` on Desktop JVM, Android, and iOS, and `Dispatchers.Default` on WasmJs where `Dispatchers.IO` does not exist. Never mutate `World` from an `ioDispatcher` or `Dispatchers.Default` coroutine: dispatch a result `Intent` into the store (or push to a channel drained on the frame thread). |

## Complete declarative 4-way separation pattern

### 1. State — Pure Contract and `ReducerStore` (zero ECS, zero Compose, zero I/O)

```kotlin
object EmotePanelContract {
    data class State(val open: Boolean = false, val entries: List<EmoteEntry> = emptyList())

    sealed interface Intent {
        data object Toggle : Intent
        data class Trigger(val emoteId: Int) : Intent
        data class SyncEntries(val entries: List<EmoteEntry>) : Intent
    }

    sealed interface Effect {
        data class PlayEmote(val emoteId: Int) : Effect
    }
}

fun emotePanelStore(
    entries: List<EmoteEntry>,
    scope: CoroutineScope,
): ReducerStore<EmotePanelContract.State, EmotePanelContract.Intent, EmotePanelContract.Effect> =
    reducerStore(EmotePanelContract.State(entries = entries), scope = scope) { state, intent ->
        when (intent) {
            EmotePanelContract.Intent.Toggle -> state.copy(open = !state.open) to null
            is EmotePanelContract.Intent.Trigger -> state to EmotePanelContract.Effect.PlayEmote(intent.emoteId)
            is EmotePanelContract.Intent.SyncEntries -> state.copy(entries = intent.entries) to null
        }
    }
```

### 2. UI — Pure Declarative Compose (zero ECS, zero `World`, zero window registry)

```kotlin
context(_: Composer)
fun EmotePanel(
    state: EmotePanelContract.State,
    onIntent: (EmotePanelContract.Intent) -> Unit,
) {
    PanelWindow(id = EmoteUiIds.PANEL, onClose = { onIntent(EmotePanelContract.Intent.Toggle) }) {
        for (entry in state.entries) {
            EmoteButton(entry, onClick = { onIntent(EmotePanelContract.Intent.Trigger(entry.id)) })
        }
    }
}
```

### 3. Behavior — Pure ECS `System` (zero Compose, zero UI registries)

```kotlin
class EmoteExecutionSystem : Family2System<EmoteRequests, Animator>(
    EmoteRequests::class,
    Animator::class,
    spec = ACTIVE_ONLY, // hoisted FamilySpec.exclude(Asleep::class)
) {
    override fun update(world: World, delta: Float) = runTick(world, delta) { _, requests, animator ->
        for (req in requests.pending) {
            playEmoteClip(animator, req.emoteId)
        }
        requests.pending.clear()
    }
}
```

### 4. ViewModel / Coordinator — `SceneBridge` + `ContextualEffectDrainer` + Declarative `ui(bridge = ...)`

```kotlin
class FrameContext {
    lateinit var world: World
        internal set
    var delta: Float = 0f
        internal set
    var localActor: Entity? = null
        internal set
}

class SceneUiModel(
    entries: List<EmoteEntry>,
    parentScope: CoroutineScope,
) : SceneBridge {
    private val drainer = ContextualEffectDrainer<FrameContext>()
    private val frame = FrameContext()

    val emote = emotePanelStore(entries, scope = parentScope.childStoreScope())
    val speed = MutableStateFlow<SpeedReadout?>(null)

    init {
        drainer.bind(
            store = emote,
            closeWithDrainer = true, // closes store automatically when scene disposes
            sync = { ctx, _ ->
                if (ctx.localActor != null && togglePressed(ctx.world)) {
                    emote.dispatch(EmotePanelContract.Intent.Toggle)
                }
            },
            onEffect = { ctx, effect ->
                val actor = ctx.localActor ?: return@bind
                when (effect) {
                    is EmotePanelContract.Effect.PlayEmote ->
                        ctx.world.emoteRequests(actor).pending += EmoteRequest(effect.emoteId)
                }
                // For async disk/network I/O, launch off the frame thread on ioDispatcher:
                // emote.coroutineScope.launch(ioDispatcher) {
                //     val loaded = fetchFromDiskOrNet()
                //     emote.dispatch(EmotePanelContract.Intent.SyncEntries(loaded))
                // }
            },
        )
        drainer.onSync { ctx -> speed.value = projectSpeed(ctx) }
    }

    override fun beforeAdvance(world: World, delta: Float) {
        populate(world, delta)
        drainer.drainEffects(frame) // UI clicks reach ECS on this frame (0-frame lag)
    }

    override fun afterAdvance(world: World, delta: Float) {
        populate(world, delta)
        drainer.sync(frame) // Fresh ECS state synced right before Compose draws
    }

    override fun close() = drainer.close()

    private fun populate(world: World, delta: Float) {
        frame.world = world
        frame.delta = delta
        frame.localActor = world.localActor() // resolved once per frame for every bound store
    }
}

// Declarative Compose root — reads typed stores directly via collectAsState(), zero World registry:
context(_: Composer)
fun SceneOverlay(model: SceneUiModel) {
    val speed by model.speed.collectAsState()
    val emote by model.emote.collectAsState()

    Box(Modifier.fillMaxSize()) {
        speed?.let { SpeedMeter(it) }
        if (emote.open) EmotePanel(emote, model.emote::dispatch)
    }
}

// Paired declaratively at the app/UI host boundary — headless/SimulationOnly hosts omit ui(...):
scene("play") {
    runProject(project)
    ui(bridge = { SceneUiModel(project.content[Emotes].orEmpty(), session.coroutineScope) }) { model ->
        SceneOverlay(model)
    }
}

// Or keep the stateless SceneBridgeHandle<T> when lifecycle hooks or tests also resolve bridge(handle):
scene("play") {
    runProject(project)
    val model = bridge { SceneUiModel(project.content[Emotes].orEmpty(), session.coroutineScope) }
    ui(model) { active -> SceneOverlay(active) }
}
```

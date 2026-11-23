# State, UI, Behavior Separation and Coroutine Dispatchers

Reference for `awake-state-management`. Follow this 4-layer separation and dispatcher table whenever
you add an in-game HUD window, panel, or gameplay screen over an Awake ECS `SceneSession`.

## Dispatcher strategy across Desktop, Android, iOS, and WasmJs

| Work | Dispatcher / Thread | Rule |
|---|---|---|
| ECS `System.update`, `SceneBridge` (`beforeAdvance` / `afterAdvance`), `ContextualEffectDrainer`, `ReducerStore.dispatch`, Compose frame | **Synchronous on the engine frame thread** | Never use `Dispatchers.Main` for engine/UI frames (on Desktop JVM `Dispatchers.Main` can bind to Swing/AWT EDT instead of the GLFW/Vulkan/WebGPU render thread). `dispatch()` uses atomic `MutableStateFlow.update` + non-suspending `Channel.trySend()`; `drainEffects()` uses `tryReceive()`. Zero coroutine launches and zero thread hops per frame. |
| Async CPU work (prewarms, glTF decode, background store work) | **`SceneSession.coroutineScope`** (`Dispatchers.Default`, child of `AppCoroutineScope`) | Derive every HUD/panel store's scope via `session.coroutineScope.childStoreScope()` so uncaught exceptions reach `AppErrorHandler` and session teardown cancels every child store automatically. Closing one store cancels only its own child `SupervisorJob`. |
| Blocking disk, asset, or network I/O | **Awake's `ioDispatcher`** (`com.awakekt.awake.core.io.ioDispatcher`) | Maps to `Dispatchers.IO` on Desktop JVM, Android, and iOS, and `Dispatchers.Default` on WasmJs where `Dispatchers.IO` does not exist. Never mutate `World` from an `ioDispatcher` or `Dispatchers.Default` coroutine: dispatch a result `Intent` into the store (or push to a channel drained on the frame thread). |

## Complete 4-way separation pattern

### 1. State — Pure Contract and `ReducerStore` (zero ECS, zero Compose, zero I/O)

```kotlin
object EmoteWindowContract {
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

fun emoteWindowStore(
    entries: List<EmoteEntry>,
    scope: CoroutineScope,
): ReducerStore<EmoteWindowContract.State, EmoteWindowContract.Intent, EmoteWindowContract.Effect> =
    reducerStore(EmoteWindowContract.State(entries = entries), scope = scope) { state, intent ->
        when (intent) {
            EmoteWindowContract.Intent.Toggle -> state.copy(open = !state.open) to null
            is EmoteWindowContract.Intent.Trigger -> state to EmoteWindowContract.Effect.PlayEmote(intent.emoteId)
            is EmoteWindowContract.Intent.SyncEntries -> state.copy(entries = intent.entries) to null
        }
    }
```

### 2. UI — Pure retained Compose View (zero ECS, zero `World`, zero store lifecycle)

```kotlin
context(_: Composer)
fun EmoteWindowContent(
    state: EmoteWindowContract.State,
    onIntent: (EmoteWindowContract.Intent) -> Unit,
) {
    PanelWindow(id = EmoteUiIds.WINDOW, onClose = { onIntent(EmoteWindowContract.Intent.Toggle) }) {
        for (entry in state.entries) {
            EmoteButton(entry, onClick = { onIntent(EmoteWindowContract.Intent.Trigger(entry.id)) })
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

### 4. Wiring — Session-level `SceneBridge` + `ContextualEffectDrainer`

```kotlin
class HudFrameContext {
    lateinit var world: World
        internal set
    var delta: Float = 0f
        internal set
    var localPlayer: Entity? = null
        internal set
}

class InGameUiBridge(
    private val parentScope: CoroutineScope,
) : SceneBridge {
    private val drainer = ContextualEffectDrainer<HudFrameContext>()
    private val frame = HudFrameContext()

    fun childStoreScope(dispatcher: CoroutineDispatcher? = null): CoroutineScope =
        parentScope.childStoreScope(dispatcher)

    fun bindEmoteWindow(entries: List<EmoteEntry>, registry: WindowRegistry) {
        val store = emoteWindowStore(entries, scope = childStoreScope())
        registry.register(EmoteUiIds.WINDOW, visible = { store.value.open }) {
            EmoteWindowContent(store.collectAsState().value, store::dispatch)
        }
        drainer.bind(
            store = store,
            closeWithDrainer = true, // closes store automatically when bridge closes
            sync = { ctx, _ ->
                if (ctx.localPlayer != null && togglePressed(ctx.world)) {
                    store.dispatch(EmoteWindowContract.Intent.Toggle)
                }
            },
            onEffect = { ctx, effect ->
                val me = ctx.localPlayer ?: return@bind
                when (effect) {
                    is EmoteWindowContract.Effect.PlayEmote ->
                        ctx.world.emoteRequests(me).pending += EmoteRequest(effect.emoteId)
                }
                // For async disk/network I/O, launch off the frame thread on ioDispatcher:
                // store.coroutineScope.launch(ioDispatcher) {
                //     val loaded = fetchFromDiskOrNet()
                //     store.dispatch(EmoteWindowContract.Intent.SyncEntries(loaded))
                // }
            },
        )
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
        frame.localPlayer = world.localPlayer() // resolved once per frame for all windows
    }
}

// Installed once at the app/UI host boundary — never runs on headless/SimulationOnly hosts:
scene("game") {
    runProject(project)
    bridge { buildGameUiBridge(project, session.coroutineScope, windowRegistry) }
    ui { InGameUiRoot(windowRegistry) }
}
```

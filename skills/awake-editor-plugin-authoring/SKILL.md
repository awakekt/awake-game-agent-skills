---
name: awake-editor-plugin-authoring
description: Write an editor plugin for Awake Studio or any other Awake editor host against the public Apache contract com.awakekt.awake.editor:contract. Use before writing a plugin manifest, an EditorPlugin, providers, an asset converter, or a project plugin reference.
license: Apache-2.0
metadata:
  author: awake
  last-updated: '2026-10-04'
  keywords: Awake, editor plugin, EditorPlugin, PluginManifest, EditorProvider, ProviderRegistry, AssetConverter, .awakeplugin, ViewportToolProvider, SceneSystemsProvider, ComponentInspectorProvider, EditHistory, undo
---

# Writing an Awake Editor Plugin

A plugin compiles against `com.awakekt.awake.editor:contract` (Apache-2.0) and nothing from a
particular editor. Any host that implements the contract can install it; Awake Studio is one such
host and adds discovery, signature checks and entitlement on top. Keep plugin runtime out of the
plugin: whatever a game needs at run time belongs in an Awake Core module or the game, and the
plugin only edits data that runtime reads.

## Plugin Contract Components

### 1. Plugin Manifest (`PluginManifest`)

Serialized descriptor for marketplace and `.awakeplugin` archives:

```kotlin
data class PluginManifest(
    val id: String,                        // reverse-domain (e.g. "com.example.terrain")
    val name: String,                      // human-readable display name
    val version: String,                   // SemVer (e.g. "1.2.0")
    val author: String = "Community",
    val description: String = "",
    val entrypointClass: String = "",      // FQN implementing EditorPlugin; if non-blank, archive MUST have payload bytes
    val requiredApiVersion: Int = 1,
    val minEngineVersion: String? = null,
    val supportedPlatforms: List<String> = emptyList(),
    val targetJvmVersion: Int? = null,
    val dependencies: List<PluginDependency> = emptyList(),
    val requiredLicense: String? = null,   // entitlement a host must hold before activation; null = free
    val category: String = "Tools",
    val tags: List<String> = emptyList(),
    val documentationUrl: String = "",
)
```

> **⚠️ Important**: `contributesDockTab` and `dockTabTitle` were retired. Bottom panel contributions are
> now declared by the plugin's `createProviders()` returning providers with `EditorProviderKind.BottomPanel`.
> Never re-add these manifest fields.

### 2. Plugin Lifecycle (`EditorPlugin` + `PluginLifecycle`)

```kotlin
// The named extension point interface (keeps "Editor" prefix)
interface EditorPlugin {
    val metadata: PluginMetadata               // use PluginMetadata, NOT EditorPluginMetadata

    fun createProviders(): List<EditorProvider> // return providers; no direct registry mutation
}

// Optional: for plugins that own resources beyond their providers
interface PluginLifecycle {
    fun dispose()                              // called after providers are unregistered
}
```

### 3. Editor Providers (`EditorProvider` & `EditorProviderKind`)

Plugins extend editor capabilities by returning typed `EditorProvider` implementations from `createProviders()`:

The full reference is the contract README:
<https://github.com/awakekt/awake/blob/main/awake/editor/contract/README.md>. Implement the
interface for the slot you want; each fixes its own `kind` and defaults its codec to
`NoProviderConfiguration`, so a provider without configuration needs neither.

| Kind | Implement | Use it for | The host keeps |
|---|---|---|---|
| `BottomPanel`, `Sidebar`, `InspectorPanel` | `PanelProvider` (set `kind`) | A panel of your own UI | The tab, labelled with `metadata.displayName` |
| `Toolbar` | `ToolbarProvider` | A button or small control | Placement; `displayName` is the tooltip |
| `Workspace` | `WorkspaceProvider` | A whole central canvas: node graph, map editor | The switcher and the canvas size |
| `FloatingCard` | `FloatingCardProvider` | A card over the viewport | Docking and order (`FloatingCardDeck`) |
| `Keybinding` | `KeybindingProvider` | Shortcuts for your actions | The keymap, rebinding, conflicts |
| `EntityTemplate` | `EntityTemplateProvider` | An insertable entity with your components | The insert menu and insertion |
| `ViewportTool` | `ViewportToolProvider` | A brush or placement tool in the viewport | Which tool is active; reserved gestures such as orbit |
| `SceneSystems` | `SceneSystemsProvider` | ECS systems that run while editing: snapping, previews | The edit loop; never runs in play mode |
| `Component` | `ComponentInspectorProvider` | Inspector fields for your component type | How fields look; section order |

Asset import is `AssetConverterPlugin`, not a provider kind. `Asset`, `Environment`, `Animation` and
`Build` are reserved: the contract gives them no behaviour yet, so a plugin that relies on one is
tied to whichever host interprets it.

#### Drawing UI

Panels, toolbar controls, workspaces and cards draw with Awake Compose
(`context(_: Composer)`) and Core's shadcn recipes, never an editor's own UI library. They change
data the game runtime reads; they never hold game state themselves.

```kotlin
class WeatherPanel : PanelProvider {
    override val metadata = ProviderMetadata(ProviderId("com.example.weather.panel"), "Weather")
    override val kind = EditorProviderKind.BottomPanel

    context(_: Composer)
    override fun content() {
        ShadcnButton("Make it rain", onClick = { /* change data the game runtime reads */ })
    }
}
```

#### Keys and templates

`Keybinding.execute()` takes no host context: act on your plugin's own state and return true when
you handled the key. `EntityTemplate.configure(world, entity)` adds scene components only; the
render systems build GPU resources from them.

#### Scene edits and undo

Two rules hold for every scene hook (decision
[D36](https://github.com/awakekt/awake/blob/main/docs/architecture/decisions/D36-scene-bound-editor-hooks.md)):

1. **Every scene edit goes through the host's undo.** Run an `EditCommand` with
   `EditHistory.execute`, or, for a drag that writes live values each frame, `record` one command
   when it ends. Never keep a private undo stack. `InspectorFieldScope` fields record their own
   steps.
2. **Edit-time systems never run in play mode.** `SceneSystemsProvider.createSystems()` runs only on
   the edited world. Gameplay is runtime code the game registers, not a plugin system.

A tool reads the pointer ray from `ViewportContext.pointerRay()`, edits live during the drag, and
records one undo step on release:

```kotlin
class PlaceMarkerTool : ViewportToolProvider {
    override val metadata = ProviderMetadata(ProviderId("com.example.marker.tool"), "Place marker")
    private var before: Vec3f? = null

    override fun isApplicable(context: ViewportContext) =
        context.selection.primary?.let { context.world.get<Marker>(it) } != null

    override fun onPointerDrag(context: ViewportContext): Boolean {
        val marker = context.selection.primary?.let { context.world.get<Marker>(it) }
        val hit = context.pointerRay()?.intersectGroundPlane()
        if (marker == null || hit == null) return false
        if (before == null) before = marker.position.copy()
        marker.position.set(hit.x, hit.y, hit.z)
        return true
    }

    override fun onPointerUp(context: ViewportContext) {
        val marker = context.selection.primary?.let { context.world.get<Marker>(it) } ?: return
        val start = before ?: return
        before = null
        val end = marker.position.copy()
        context.history.record(object : EditCommand {
            override val label = "Place marker"
            override fun apply() { marker.position.set(end.x, end.y, end.z) }
            override fun revert() { marker.position.set(start.x, start.y, start.z) }
        })
    }
}
```

An inspector reads the component defensively, since a system may remove it before the fields draw:

```kotlin
class MarkerInspector : ComponentInspectorProvider {
    override val metadata = ProviderMetadata(ProviderId("com.example.marker.inspector"), "Marker")
    override val componentType = Marker::class

    override fun fields(scope: InspectorFieldScope, world: World, entity: Entity) {
        val marker = world.get<Marker>(entity) ?: return
        scope.vector("Position", marker.position)
        scope.scalar("Size", marker.size) { marker.size = it }
    }
}
```

### 4. `PluginRegistry` & `ProviderRegistry`

The host wires `PluginRegistry` → `ProviderRegistry`:

```kotlin
val providerRegistry = ProviderRegistry()        // was EditorProviders
val pluginRegistry = PluginRegistry(providerRegistry) // was EditorPluginRegistry
pluginRegistry.install(myPlugin)                 // calls myPlugin.createProviders() atomically
```

### 5. Asset Converters (`AssetConverterPlugin`)

```kotlin
interface AssetConverterPlugin : EditorPlugin {
    fun getConverters(): List<AssetConverter>
    override fun createProviders(): List<EditorProvider> = emptyList() // default no-op
}
```

---

## Project Plugin Reference

Projects declare their active plugins in `awake.project.json` using `AwakeProjectPluginReference` in `:awake:project`:

```kotlin
data class AwakeProjectPluginReference(
    val id: String,
    val path: String,               // project-relative path to the plugin bundle
    val version: String = "",
    val sha256: String? = null,     // optional content integrity pin
    val entrypointClass: String? = null,
    val required: Boolean = false,
)
```

- `sha256`: Prevents tampered or mismatched plugin binaries.
- `entrypointClass`: The fully qualified name implementing `EditorPlugin`.

## Packaging and entitlement

- Ship a `.awakeplugin` archive with its `plugin.json` manifest. A non-blank `entrypointClass`
  requires a non-empty bytecode payload; hosts reject a metadata-only archive that declares one.
- A plugin is free unless `requiredLicense` names an entitlement. The contract names no product;
  each host maps the identifier to its own tiers (Studio uses `awake.pro.*`).
- Use the canonical names (`PluginId`, `ProviderRegistry`, ...), never the deprecated `Editor*`
  aliases listed in `awake-core-editor`.

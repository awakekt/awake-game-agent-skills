---
name: awake-editor-plugin-authoring
description: Write an editor plugin for Awake Studio or any other Awake editor host against the public Apache contract com.awakekt:awake-editor-contract. Use before writing a plugin manifest, an EditorPlugin, providers, an asset converter, or a project plugin reference.
license: Apache-2.0
metadata:
  author: awake
  last-updated: '2026-10-03'
  keywords: Awake, editor plugin, EditorPlugin, PluginManifest, EditorProvider, ProviderRegistry, AssetConverter, .awakeplugin
---

# Writing an Awake Editor Plugin

A plugin compiles against `com.awakekt:awake-editor-contract` (Apache-2.0) and nothing from a
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

| `EditorProviderKind` | Purpose | Typed sub-interface |
|---|---|---|
| `Component` | Custom component panels | `ComponentProvider` |
| `Asset` | Asset import/processing | `AssetProvider` |
| `Environment` | Sky, lighting, ambient | `EnvironmentProvider` |
| `Animation` | Animation curves/clips | `AnimationProvider` |
| `Build` | Build steps & export | `BuildProvider` |
| `BottomPanel` | Docked bottom tray panels | (raw `EditorProvider`) |
| `Toolbar` | Toolbar actions & controls | (raw `EditorProvider`) |
| `Sidebar` | Left sidebar tabs | (raw `EditorProvider`) |
| `InspectorPanel` | Right inspector tabs | (raw `EditorProvider`) |
| `Keybinding` | Keyboard shortcut maps | (raw `EditorProvider`) |
| `Workspace` | Central canvas (viewport, visual scripting) | (raw `EditorProvider`) |
| `EntityTemplate` | Insertable entity archetypes | (raw `EditorProvider`) |
| `SceneSystems` | ECS systems injected into the scene loop | (raw `EditorProvider`) |
| `ViewportTool` | Interactive viewport tools | (raw `EditorProvider`) |
| `FloatingCard` | Floating HUD cards over the 3D viewport | (raw `EditorProvider`) |

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

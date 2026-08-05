# mach-vk generator

`gen.py` emits the mach-vk declaration layers from the Vulkan registry, the same
way [mach-gl](https://github.com/briar-systems/mach-gl)'s `tools/gen.py` emits
its layers from `gl.xml`: a pinned registry snapshot in, deterministic mach
sources out, with a CI drift check that regenerates and diffs so the pin and the
committed sources cannot fall apart.

The generator covers the **core** Vulkan API (1.0–1.3) plus a curated extension
allowlist — the `EXTENSIONS` list at the top of `gen.py`:

| extension | what it brings |
| --- | --- |
| `VK_KHR_surface` | the surface handle and physical-device surface queries |
| `VK_KHR_swapchain` | swapchain creation, image acquisition, and present |
| `VK_KHR_xlib_surface` | X11 surface creation |
| `VK_KHR_wayland_surface` | Wayland surface creation |
| `VK_KHR_win32_surface` | Win32 surface creation |
| `VK_EXT_metal_surface` | Metal (MoltenVK) surface creation |
| `VK_EXT_debug_utils` | debug messengers, object names, and command labels |

Widening the allowlist is the whole cost of adding an extension: append its name
and regenerate. Video and Vulkan SC stay out of scope.

## Registry

`tools/vk.xml` is a verbatim snapshot of `xml/vk.xml` from
[KhronosGroup/Vulkan-Docs](https://github.com/KhronosGroup/Vulkan-Docs), pinned
at the `v1.4.356` release — the exact commit is recorded in `REGISTRY_COMMIT`.
`vk.xml` is the single machine-readable source of the Vulkan API — types,
handles, enums, bitmasks, structs, commands, and the feature/extension sets that
gate them.

## Output layout

`gen.py` emits into `src/`, one layer per concern:

```
src/
  types.mach    opaque handle aliases (generated); a leaf layer, imports nothing
  enums.mach    enumerant, bitmask, and extension-name constants (generated)
  structs.mach  struct and union records with C-identical layout, plus the PFN_*
                callback aliases (generated)
  c.mach        raw command table + loaders (generated): one pub var function
                pointer per command, plus load_global / load_instance /
                load_device walking the proc-addr chains
  vk.mach       library surface (generated): re-exports every symbol under vk.*
```

The layer boundaries follow the C type graph's actual dependency order:
`types` → `structs` → `c`. Handles are leaves — pointer-sized aliases that
reference nothing — so they sit alone at the bottom. The `PFN_*` callback
aliases share `structs.mach` with the records because the two are *mutually*
recursive in C: `VkAllocationCallbacks` holds a `PFN_vkAllocationFunction`
member, while `PFN_vkDebugUtilsMessengerCallbackEXT` takes a
`VkDebugUtilsMessengerCallbackDataEXT*`. Mach refuses a circular module
dependency, so a cycle in the type graph has to live inside one module.

This is mach-gl's shape adapted to Vulkan's larger type surface: GL has only
commands and enums, so mach-gl needs `c` + `enums`; Vulkan adds a rich type
system (handles, structs, unions, flags), so the types and structs earn their
own layers. Unlike mach-gl there is deliberately **no idiomatic wrapper layer**
(`cmd.mach`): Vulkan's ergonomics and safety belong in the engine's RHI, not the
binding (see the repository README's non-goals). mach-vk stays raw declarations
plus the loader chain.

## Approach

1. **Parse.** Walk the `<feature>` blocks for core 1.0–1.3 (filtering to the
   `vulkan` api, skipping the `vulkansc` variants), then the allowlisted
   `<extension>` blocks in `EXTENSIONS` order, applying `<require>` and
   `<remove>` to accumulate the live set of types, enums, and commands, then
   resolve each through the registry's `<type>`, `<enums>`, and `<command>`
   graphs. A transitive closure over struct members and command signatures pulls
   in every reachable type, stopping at scalar leaves. A `<require depends=...>`
   guard is honoured: a block is taken only when every core version and
   extension it names is itself generated. An enumerant inside an extension
   takes that extension's number as its `extnumber` unless it names another's.
2. **Map types.** Scalar base types resolve straight to mach scalars (`uint32_t`
   → `u32`, `VkBool32` → `u32`, `VkDeviceSize` → `u64`, `VkFlags` → `u32`,
   `VkFlags64` → `u64`); enums are their underlying `i32` and bitmasks their
   underlying `u32`/`u64` at use sites, with the enumerant values emitted as
   constants in `enums.mach`. Handles (dispatchable and non-dispatchable alike)
   are opaque pointer-sized `def` aliases; structs and unions become `rec`s and
   `uni`s with C-identical layout; `PFN_*` function pointers become `def`
   fun-type aliases. `pNext` is always a raw `ptr`, and `const char*` /
   `const char* const*` map to `*u8` / `**u8`. The OS-header leaves the platform
   surface extensions touch need no headers and no target gating: `Display*`,
   `wl_surface*`, and `const CAMetalLayer*` are opaque and collapse to `ptr` the
   same way `void*` does, `HINSTANCE`/`HWND` are pointer-sized by value, and an
   Xlib `Window`/`VisualID` is an XID (`u64` on the LP64 targets mach builds
   for). The generated declarations are therefore identical on every target.
3. **Classify dispatch.** Each command is tagged global, instance, or device by
   the type of its first parameter, which decides the resolver that fills it:
   - **global** — no dispatchable handle (`vkCreateInstance`,
     `vkEnumerateInstance*`): resolved via `vkGetInstanceProcAddr(nil, name)`.
   - **instance** — `VkInstance` / `VkPhysicalDevice` first parameter: resolved
     via `vkGetInstanceProcAddr(instance, name)`.
   - **device** — `VkDevice` / `VkQueue` / `VkCommandBuffer` first parameter:
     resolved via `vkGetDeviceProcAddr(device, name)` for dispatch without the
     instance trampoline.
4. **Emit deterministically.** Stable ordering, C names and C-faithful types, so
   `gen.py check` produces a byte-identical diff against the committed sources.

## Usage

```
tools/gen.py            regenerate the src/*.mach declaration layers
tools/gen.py check      diff a fresh generation against the committed sources;
                        nonzero exit on drift (CI's generation-drift job)
```

Python standard library only, matching mach-gl.

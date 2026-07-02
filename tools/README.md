# mach-vk generator

`gen.py` emits the mach-vk declaration layers from the Vulkan registry, the same
way [mach-gl](https://github.com/briar-systems/mach-gl)'s `tools/gen.py` emits
its layers from `gl.xml`: a pinned registry snapshot in, deterministic mach
sources out, with a CI drift check that regenerates and diffs so the pin and the
committed sources cannot fall apart.

**Status: scaffold.** The layout and approach below are settled and encoded in
`gen.py`, but the Vulkan emit is not yet implemented — `parse()` and the `gen_*`
emitters raise `NotImplementedError`, and running `gen.py` reports the scaffold
state. The `src/*.mach` files in the tree today are hand-written placeholders
(a minimal compiling loader skeleton) that generation will replace wholesale.

## Registry

`tools/vk.xml` will be a verbatim snapshot of `xml/vk.xml` from
[KhronosGroup/Vulkan-Docs](https://github.com/KhronosGroup/Vulkan-Docs), pinned
at an exact commit recorded in `REGISTRY_COMMIT`. The file is not yet vendored;
it is fetched and pinned when the generator is implemented. `vk.xml` is the
single machine-readable source of the Vulkan API — types, handles, enums,
bitmasks, structs, commands, and the feature/extension sets that gate them.

## Output layout

`gen.py` emits into `src/`, one layer per concern:

```
src/
  types.mach    base type aliases and opaque handle definitions (generated)
  enums.mach    enumerant and bitmask constants (generated)
  structs.mach  struct and union records, C-identical layout (generated)
  c.mach        raw command table + loaders (generated): one pub var function
                pointer per command, plus load_global / load_instance /
                load_device walking the proc-addr chains
  vk.mach       library surface (generated): re-exports every symbol under vk.*
```

This is mach-gl's shape adapted to Vulkan's larger type surface: GL has only
commands and enums, so mach-gl needs `c` + `enums`; Vulkan adds a rich type
system (handles, structs, unions, flags), so the types and structs earn their
own layers. Unlike mach-gl there is deliberately **no idiomatic wrapper layer**
(`cmd.mach`): Vulkan's ergonomics and safety belong in the engine's RHI, not the
binding (see the repository README's non-goals). mach-vk stays raw declarations
plus the loader chain.

## Approach

1. **Parse.** Walk `<feature api="vulkan">` for core 1.0–1.3, applying
   `<require>` and `<remove>` to accumulate the live set of types, enums, and
   commands, then resolve each through the registry's `<type>`, `<enums>`, and
   `<command>` graphs. Extensions are added on demand, gated the same way.
2. **Map types.** Vulkan base C types resolve to mach scalars (`uint32_t` →
   `u32`, `VkBool32` → `u32`, `VkDeviceSize` → `u64`, ...); dispatchable and
   non-dispatchable handles are opaque `ptr`; structs and unions become `rec`s
   with C-identical layout; `PFN_*` function pointers become `def` typedefs.
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

## Usage (once implemented)

```
tools/gen.py            regenerate the src/*.mach declaration layers
tools/gen.py check      diff a fresh generation against the committed sources;
                        nonzero exit on drift (CI's generation-drift job)
```

Python standard library only, matching mach-gl.

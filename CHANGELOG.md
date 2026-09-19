# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Moved std to 6.0.0, declared as the range `^6.0` with the `dep/std` gitlink (980386e) as the pin. std 6 is a major, and a root project's std override replaces every dependency's std, so a consumer on std 6 could not use this library while it declared std 5. No source change was needed: the bindings and the example use only `std.runtime`, `std.print`, `std.process.env` and `std.types`, none of the sort, heap, map, set, constant-time or buffers surface std 6 reshaped. `[project].mach` rises to `^5.9`, the family seed, and the code was verified on mach 5.9.0.

## [0.4.0] - 2026-09-19

### Changed
- Moved std to 5.7.1, declared as the range `^5.7.1` with the `dep/std` gitlink as the pin. An exact tag below a root's range conflicts on every std minor, and a range resolves alongside a root written by `mach init`. A root project's std override replaces every dependency's std, so a consumer on std 5 could not use this library while it pinned std 4. No source change was needed: the bindings and the example touch none of the clock, cancellation, timer or `buffers.Source` surface std 5 reshaped. `[project].mach` rises to `^5.5.2`, the floor std 5.7.1 itself requires, and the code was verified on exactly mach 5.5.2.
- Release runs are serialized per tag, as the shared release workflow now requires. A duplicate tag-push delivery waits and then ends with nothing to do.
- The manifest declares a compiler range, so mach 5.3 and later build it without a warning. It is `^5.5.2` in this release.
- The copyright belongs to Briar Systems LLC.
- Releases publish through the family's shared release workflow. A pushed `v*` tag runs the version and changelog checks, the full CI tier, and then publishes the GitHub release with the version's changelog section as notes.

## [0.3.1] - 2026-09-16

### Changed
- Moved std to 4.0.0. No source change was needed, since the bindings and the example use none of the names std 4 removed or moved. Building with std 4.0.0 needs mach 5.2.0 or later.

### Fixed
- The README states the bare `use vk;` rule as mach defines it, the entry shared by the default library artifacts, and links mach's description.

## [0.3.0] - 2026-09-16

### Changed
- Migrated to Mach 5.0 and std 2.1.0. The manifest states complete profiles and default markers, std is pinned by its `dep/std` gitlink in place of `mach.lock`, and CI pulls with `mach dep pull .`. Consumers declare the dependency as `[dep.vk]`.
- The generator reserves the Mach 5 keywords (`sel`, `tag`, `each`, `error`, `in`). No generated identifier changed.
- The example reads `VK_EXAMPLE_LINK_ONLY` through the std 2.1 `res[opt[usize], EnvError]` surface.
- Moved std to 3.2.0. No source change was needed, since the bindings and the example use none of the io runtime surface std 3 reshaped. Building with std 3.2.0 needs mach 5.1.0 or later.
- CI follows the family contract (briar-systems/mach#3447). One `ci.yml` calls the shared tiered library workflow and ends in a `gate` job. Pull requests into dev run the linux leg and the generation drift check, and pull requests into main also run the Windows and Darwin loader legs. `mach fmt --check` now runs.
- `tools/gen.py` pipes its output through `mach fmt -`, so the committed sources are exactly what the formatter writes. The sources were reformatted once to match.

## [0.2.0] - 2026-08-08

### Added
- The worked example moved from a `test/smoke` sub-project to a root `example` artifact, so the library no longer path-depends on its own parent. That shape was unusable on a Windows host and blocked the Windows loader leg.

### Changed
- CI builds and runs the example natively on Linux, Windows, and Darwin, and cross-builds the library for all three targets.

Released so consumers can reach the surface and swapchain declarations from `main`. boom needs them for its Vulkan renderer (briar-systems/boom#27).

### Changed
- manifest: Re-touched to RFC-exact totality per mach#1964/mach#1979.

## [0.1.0] - 2026-07-07

### Changed
- manifest: Migrated manifest format to V2 and configured Vulkan static library artifact.

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
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

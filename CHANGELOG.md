# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

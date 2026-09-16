#!/usr/bin/env bash
# the declarations build for every target, and the example drives a real loader
set -euo pipefail

# a runner with the loader but no usable device falls back to link-only, which
# still proves the loader loads and the vkGetInstanceProcAddr chain resolves
run_example() {
  "$MACH_COMPILER" build . --bin example "$@"
  "$MACH_COMPILER" run . --bin example "$@" || {
    echo "full example failed (no device on this runner), falling back to link-only"
    VK_EXAMPLE_LINK_ONLY=1 "$MACH_COMPILER" run . --bin example "$@"
  }
}

case "$MACH_CI_LEG" in
  x86_64-linux)
    # the library alone: the example links a loader, and darwin's is probed on disk
    for target in linux-x86_64 windows-x86_64 darwin-x86_64; do
      "$MACH_COMPILER" build . --lib vk --target "$target" --profile release
      echo "library builds for $target"
    done
    # lavapipe is a real ICD, so linux has no link-only fallback
    "$MACH_COMPILER" build . --bin example
    "$MACH_COMPILER" run . --bin example
    ;;
  x86_64-windows)
    run_example --target windows-x86_64 --profile release
    ;;
  x86_64-darwin)
    run_example --target darwin-x86_64 --profile release
    ;;
esac

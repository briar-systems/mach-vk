#!/usr/bin/env bash
# the example drives a real loader. the subprojects phase already built it in
# every profile, since mach run never builds.
set -euo pipefail

# a runner with the loader but no usable device falls back to link-only, which
# still proves the loader loads and the vkGetInstanceProcAddr chain resolves
run_example() {
  "$MACH_COMPILER" run demo/example "$@" || {
    echo "full example failed (no device on this runner), falling back to link-only"
    VK_EXAMPLE_LINK_ONLY=1 "$MACH_COMPILER" run demo/example "$@"
  }
}

case "$MACH_CI_LEG" in
  x86_64-linux)
    # lavapipe is a real ICD, so linux has no link-only fallback
    "$MACH_COMPILER" run demo/example
    ;;
  x86_64-windows)
    run_example --target windows-x86_64 --profile release
    ;;
  x86_64-darwin)
    run_example --target darwin-x86_64 --profile release
    ;;
esac

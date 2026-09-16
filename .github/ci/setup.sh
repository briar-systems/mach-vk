#!/usr/bin/env bash
# the vulkan loader each leg runs the example against. linking records the
# loader by name, so only the loader itself must be present, at run time.
set -euo pipefail

case "$MACH_CI_LEG" in
  x86_64-linux)
    vulkaninfo --summary
    ;;
  x86_64-windows)
    # a headless runner may lack the loader, and the runtime-only installer is enough
    pwsh -NoProfile -Command '
      $ErrorActionPreference = "Stop"
      if (-not (Test-Path "C:\Windows\System32\vulkan-1.dll")) {
        $installer = Join-Path $env:RUNNER_TEMP "vulkan-runtime.exe"
        curl.exe -fsSL "https://sdk.lunarg.com/sdk/download/latest/windows/vulkan-runtime.exe" -o $installer
        Start-Process -FilePath $installer -ArgumentList "/S" -Wait
      }
      if (-not (Test-Path "C:\Windows\System32\vulkan-1.dll")) {
        Write-Error "vulkan-1.dll not present after runtime install"
        exit 1
      }
      Write-Host "vulkan-1.dll present"
    '
    ;;
  x86_64-darwin)
    brew install molten-vk
    ls -la /usr/local/lib/libMoltenVK.dylib
    ;;
esac

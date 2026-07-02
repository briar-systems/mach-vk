#!/usr/bin/env python3
# gen.py: emit the generated mach-vk binding layers from the Vulkan registry.
#
# SCAFFOLD. this file lays out the generation approach mirroring mach-gl's
# tools/gen.py, but the Vulkan emit is not yet implemented: parse() and the
# gen_* emitters raise NotImplementedError, and main() reports the scaffold
# state instead of writing sources. see tools/README.md for the full plan.
#
# tools/vk.xml will be a verbatim snapshot of xml/vk.xml from
# KhronosGroup/Vulkan-Docs, pinned at REGISTRY_COMMIT:
#   https://raw.githubusercontent.com/KhronosGroup/Vulkan-Docs/<commit>/xml/vk.xml
#
# usage (once implemented):
#   tools/gen.py            regenerate the src/*.mach declaration layers
#   tools/gen.py check      regenerate to memory and diff against the committed
#                           sources; exit nonzero (and print a unified diff) on
#                           any drift — this is what CI's generation-drift job runs
#
# stdlib only; output must be deterministic so the committed sources and the
# registry pin cannot drift apart.

import difflib
import os
import re
import sys
import xml.etree.ElementTree as ET

# TODO: pin the exact KhronosGroup/Vulkan-Docs commit when tools/vk.xml is
# vendored. left empty until the registry snapshot lands.
REGISTRY_COMMIT = ""

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XML = os.path.join(ROOT, "tools", "vk.xml")
SRC = os.path.join(ROOT, "src")

# the declaration layers this generator emits. the raw command table and the
# loader chain live in c.mach; the surface (vk.mach) re-exports every symbol.
OUTPUTS = ("types.mach", "enums.mach", "structs.mach", "c.mach", "vk.mach")

# mach reserved keywords (grammar.md); a generated identifier matching one
# exactly is renamed with a trailing underscore.
KEYWORDS = set(
    "asm brk cnt def ext fin for fun fwd if nil or pub rec ret test uni use val var".split()
)

# Vulkan base C type -> mach scalar type. VkBool32, VkDeviceSize, and the
# handle/enum/flags families resolve through the registry's <type> graph rather
# than this table; it seeds the primitive leaves.
SCALAR = {
    "void": "",
    "char": "u8",
    "int8_t": "i8",
    "uint8_t": "u8",
    "int16_t": "i16",
    "uint16_t": "u16",
    "int32_t": "i32",
    "uint32_t": "u32",
    "int64_t": "i64",
    "uint64_t": "u64",
    "int": "i32",
    "float": "f32",
    "double": "f64",
    "size_t": "u64",
    "VkBool32": "u32",
    "VkDeviceSize": "u64",
    "VkDeviceAddress": "u64",
    "VkSampleMask": "u32",
    "VkFlags": "u32",
    "VkFlags64": "u64",
}

# dispatch tiers, keyed by the type of a command's first parameter. a command's
# tier decides which resolver fills it: load_global (no dispatchable handle),
# load_instance (VkInstance / VkPhysicalDevice), or load_device (VkDevice /
# VkQueue / VkCommandBuffer, reachable through vkGetDeviceProcAddr).
GLOBAL_COMMANDS = (
    "vkEnumerateInstanceVersion",
    "vkEnumerateInstanceExtensionProperties",
    "vkEnumerateInstanceLayerProperties",
    "vkCreateInstance",
)
INSTANCE_DISPATCH = ("VkInstance", "VkPhysicalDevice")
DEVICE_DISPATCH = ("VkDevice", "VkQueue", "VkCommandBuffer")


def ident(name):
    return name + "_" if name in KEYWORDS else name


def map_c(s):
    # C type string -> raw-layer mach type: pointer depth preserved, opaque
    # handles and void* collapse to ptr, scalars resolve through SCALAR.
    raise NotImplementedError("Vulkan C-type mapping not yet implemented")


def parse():
    # parse tools/vk.xml and return the core declaration model: base types and
    # handle aliases, enum constants (including feature/extension enum extends),
    # struct and union records, and commands in feature order, each tagged with
    # its dispatch tier. walks <feature api='vulkan'> 1.0..1.3 applying requires
    # and removes, exactly as mach-gl walks the GL feature sets.
    raise NotImplementedError("Vulkan registry parse not yet implemented")


def gen_types(model):
    # types.mach: base type aliases and opaque handle definitions.
    raise NotImplementedError


def gen_enums(model):
    # enums.mach: every core enumerant and bitmask value as pub val constants.
    raise NotImplementedError


def gen_structs(model):
    # structs.mach: every core struct and union as a C-identical pub rec.
    raise NotImplementedError


def gen_c(model):
    # c.mach: one pub var function pointer per command, plus load_global,
    # load_instance, and load_device walking the proc-addr chains.
    raise NotImplementedError


def gen_vk(model):
    # vk.mach: the flat surface re-exporting every generated symbol.
    raise NotImplementedError


def render(model):
    return {
        "types.mach": gen_types(model),
        "enums.mach": gen_enums(model),
        "structs.mach": gen_structs(model),
        "c.mach": gen_c(model),
        "vk.mach": gen_vk(model),
    }


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "gen"
    if mode not in ("gen", "check"):
        sys.stderr.write("usage: tools/gen.py [gen|check]\n")
        sys.exit(2)

    try:
        model = parse()
        files = render(model)
    except NotImplementedError as e:
        sys.stderr.write(
            "tools/gen.py: scaffold — Vulkan generation not yet implemented "
            "({}).\nsee the module docstring and tools/README.md for the plan.\n".format(e)
        )
        sys.exit(2)

    if mode == "check":
        drift = False
        for name, content in files.items():
            path = os.path.join(SRC, name)
            current = ""
            if os.path.exists(path):
                with open(path) as f:
                    current = f.read()
            if current != content:
                drift = True
                diff = difflib.unified_diff(
                    current.splitlines(keepends=True),
                    content.splitlines(keepends=True),
                    fromfile="src/" + name,
                    tofile="src/" + name + " (regenerated)",
                )
                sys.stderr.writelines(diff)
        if drift:
            sys.stderr.write("\nsrc is out of date; run tools/gen.py\n")
            sys.exit(1)
        return

    os.makedirs(SRC, exist_ok=True)
    for name, content in files.items():
        with open(os.path.join(SRC, name), "w") as f:
            f.write(content)


if __name__ == "__main__":
    main()

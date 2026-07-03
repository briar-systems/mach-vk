#!/usr/bin/env python3
# gen.py: emit the generated mach-vk binding layers from the Vulkan registry.
#
# tools/vk.xml is a verbatim snapshot of xml/vk.xml from
# KhronosGroup/Vulkan-Docs pinned at the v1.4.356 release, commit
# REGISTRY_COMMIT below:
#   https://raw.githubusercontent.com/KhronosGroup/Vulkan-Docs/<commit>/xml/vk.xml
#
# usage:
#   tools/gen.py            regenerate the src/*.mach declaration layers
#   tools/gen.py check      regenerate to memory and diff against the committed
#                           sources; exit nonzero (and print a unified diff) on
#                           any drift; this is what CI's generation-drift job runs
#
# stdlib only; output is deterministic so the committed sources and the registry
# pin cannot drift apart. only the core API (Vulkan 1.0..1.3) is generated;
# extensions, video, and Vulkan SC are out of scope for this pass.

import difflib
import os
import re
import sys
import xml.etree.ElementTree as ET

REGISTRY_COMMIT = "73836865422f9e28e17069a96cceef6d0ece1ff8"

# highest core feature version generated; the registry may describe newer ones.
MAX_VERSION = 1.3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XML = os.path.join(ROOT, "tools", "vk.xml")
SRC = os.path.join(ROOT, "src")

# mach reserved keywords (grammar.md); a generated identifier matching one
# exactly is renamed with a trailing underscore.
KEYWORDS = set(
    "asm brk cnt def ext fin for fun fwd if nil or pub rec ret test uni use val var".split()
)

# Vulkan / C base scalar leaves -> mach scalar type. handles, enums, bitmasks,
# structs, unions, and function pointers resolve through the registry's <type>
# graph instead; this table is only the primitive leaves. void is handled by the
# pointer logic (a bare void return is empty, void* collapses to ptr).
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
INSTANCE_DISPATCH = ("VkInstance", "VkPhysicalDevice")
DEVICE_DISPATCH = ("VkDevice", "VkQueue", "VkCommandBuffer")

# base of the reserved enum-extension number range (registry convention).
EXT_ENUM_BASE = 1000000000

# module prefixes a referenced type carries when named from each generated file.
# types.mach names its own handles/fns bare; structs.mach reaches handles/fns
# through the types module and its own records bare; c.mach reaches both.
QUAL_TYPES = {"type": "", "record": "structs."}
QUAL_STRUCTS = {"type": "types.", "record": ""}
QUAL_C = {"type": "types.", "record": "structs."}


def ident(name):
    return name + "_" if name in KEYWORDS else name


def type_name(vk):
    # a handle / struct / union C name -> mach type name: the leading Vk stripped.
    return vk[2:] if vk.startswith("Vk") else vk


def pfn_name(vk):
    # a PFN_vk* function-pointer C name -> mach def name: the PFN_vk prefix stripped.
    if vk.startswith("PFN_vk"):
        return vk[6:]
    if vk.startswith("PFN_"):
        return vk[4:]
    return vk


def enum_name(vk):
    # a VK_* constant C name -> mach name: the VK_ prefix stripped, a leading _
    # prepended if the result would start with a digit.
    n = vk[3:] if vk.startswith("VK_") else vk
    if n and n[0].isdigit():
        n = "_" + n
    return n


def api_ok(elem):
    # an element belongs to the desktop Vulkan API unless a non-vulkan api filter
    # excludes it (e.g. api="vulkansc").
    a = elem.get("api")
    return a is None or "vulkan" in a.split(",")


def parse_c_int(s):
    # a C integer constant expression from the registry -> Python int. handles the
    # bare decimal/hex forms plus the (~N U/ULL) complement idiom the API constants
    # use for sentinel values.
    s = s.strip()
    m = re.fullmatch(r"\(?~(\d+)([uU]?[lL]*)\)?", s)
    if m:
        width = 64 if "ll" in m.group(2).lower() else 32
        mask = (1 << width) - 1
        return (~int(m.group(1))) & mask
    return int(re.sub(r"[uUlL]+$", "", s), 0)


class Command:
    def __init__(self, name, ret, params, tier):
        self.name = name
        self.ret = ret        # mach return type ("" for void)
        self.params = params  # list of (ident, mach_type)
        self.tier = tier      # "global" | "instance" | "device"


class Enum:
    def __init__(self, name, width, literal):
        self.name = name        # mach constant name
        self.width = width      # mach integer type
        self.literal = literal  # mach literal text


class Record:
    def __init__(self, name, kind, cname, fields):
        self.name = name          # mach type name
        self.kind = kind          # "rec" | "uni"
        self.cname = cname        # Vulkan C name
        self.fields = fields      # list of (ident, mach_type)


class Fn:
    def __init__(self, name, sig):
        self.name = name  # mach def name
        self.sig = sig    # mach fun(...) type


class Model:
    def __init__(self):
        self.handles = []       # list of (mach_name, c_name)
        self.fns = []           # list of Fn (funcpointer defs)
        self.records = []       # list of Record (structs/unions, registry order)
        self.enums = []         # list of Enum (flat, sorted by name)
        self.commands = []      # list of Command (feature order)


class Registry:
    def __init__(self, path):
        self.root = ET.parse(path).getroot()
        self.types = {}
        for t in self.root.findall("./types/type"):
            nm = t.get("name")
            if not nm:
                n = t.find(".//name")
                nm = n.text if n is not None else None
            if nm and nm not in self.types:
                self.types[nm] = t
        self.commands = {}
        self.aliases = {}
        for c in self.root.findall("./commands/command"):
            if c.get("alias"):
                self.aliases[c.get("name")] = c.get("alias")
            else:
                self.commands[c.find("proto/name").text] = c
        self.enum_blocks = {e.get("name"): e for e in self.root.findall("enums")}

    def category(self, name):
        t = self.types.get(name)
        return t.get("category") if t is not None else None

    def command(self, name):
        while name in self.aliases:
            name = self.aliases[name]
        return self.commands[name]


def member_base(elem):
    t = elem.find("type")
    return t.text if t is not None else None


def type_id(elem):
    # the declared name of a <type>: the name attribute, or the <name> child that
    # handles and function pointers carry inside their C declarator.
    nm = elem.get("name")
    if nm:
        return nm
    n = elem.find(".//name")
    return n.text if n is not None else None


class Generator:
    def __init__(self, reg):
        self.reg = reg
        self.handle_set = set()
        self.fn_set = set()
        self.enum_type_set = set()
        self.bitmask_set = set()
        self.struct_set = set()
        self.union_set = set()
        self.const_values = {}  # API-constant C name -> Python int (for array sizes)

    def resolve_len(self, name):
        if name in self.const_values:
            return self.const_values[name]
        raise KeyError("unresolved array-size constant: " + name)

    def bitmask_scalar(self, vk):
        under = self.reg.types[vk].find("type")
        return SCALAR[under.text if under is not None else "VkFlags"]

    def resolve_base(self, base, quals):
        # quals maps a referenced category ("type" for handles/funcpointers,
        # "record" for structs/unions) to the module prefix the emitting file
        # needs; same-module references pass "".
        if base in SCALAR:
            return SCALAR[base]
        if base in self.handle_set:
            return quals["type"] + type_name(base)
        if base in self.fn_set:
            return quals["type"] + pfn_name(base)
        if base in self.enum_type_set:
            return "i32"
        if base in self.bitmask_set:
            return self.bitmask_scalar(base)
        if base in self.struct_set or base in self.union_set:
            return quals["record"] + type_name(base)
        raise KeyError("unmapped type: " + str(base))

    def mach_type(self, base, depth, arrays, quals):
        if base == "void":
            core = "" if depth == 0 else "*" * (depth - 1) + "ptr"
        else:
            core = "*" * depth + self.resolve_base(base, quals)
        return "".join("[{}]".format(n) for n in arrays) + core

    def parse_declarator(self, elem):
        # decompose a <member>/<param>/<proto> into (base_c_type, pointer_depth,
        # [array_dims]). pointer stars sit between <type> and <name>; array
        # suffixes sit after <name>, literal or an <enum> naming an API constant.
        base = elem.find("type")
        base_name = base.text if base is not None else None
        depth = (base.tail or "").count("*") if base is not None else 0
        name = elem.find("name")
        arrays = []
        if name is not None:
            tail = [name.tail or ""]
            seen = False
            for child in list(elem):
                if child is name:
                    seen = True
                    continue
                if not seen:
                    continue
                if child.tag == "enum":
                    tail.append(str(self.resolve_len(child.text)))
                tail.append(child.tail or "")
            arrays = [parse_c_int(d) for d in re.findall(r"\[([^\]]+)\]", "".join(tail))]
        return base_name, depth, arrays

    def declarator_type(self, elem, quals):
        base, depth, arrays = self.parse_declarator(elem)
        return self.mach_type(base, depth, arrays, quals)

    def tier(self, command):
        params = command.findall("param")
        if not params:
            return "global"
        first = member_base(params[0])
        if first in DEVICE_DISPATCH:
            return "device"
        if first in INSTANCE_DISPATCH:
            return "instance"
        return "global"

    def collect(self):
        reg = self.reg
        features = [
            f for f in reg.root.findall("feature")
            if api_ok(f) and float(f.get("number")) <= MAX_VERSION
        ]

        req_types = []
        req_type_set = set()
        cmd_order = []
        cmd_set = set()
        ext_enums = []       # <enum extends=...> from core features
        const_names = []     # standalone API constants referenced by core
        const_seen = set()
        for f in features:
            for sec in ("require", "remove"):
                add_sec = sec == "require"
                for r in f.findall(sec):
                    if not api_ok(r):
                        continue
                    for c in r:
                        if not api_ok(c):
                            continue
                        if c.tag == "type" and add_sec:
                            if c.get("name") not in req_type_set:
                                req_type_set.add(c.get("name"))
                                req_types.append(c.get("name"))
                        elif c.tag == "command":
                            n = c.get("name")
                            if add_sec and n not in cmd_set:
                                cmd_set.add(n)
                                cmd_order.append(n)
                            elif not add_sec and n in cmd_set:
                                cmd_set.discard(n)
                                cmd_order.remove(n)
                        elif c.tag == "enum" and add_sec:
                            if c.get("extends"):
                                ext_enums.append(c)
                            elif not any(c.get(k) for k in ("value", "bitpos", "offset", "alias")):
                                if c.get("name") not in const_seen:
                                    const_seen.add(c.get("name"))
                                    const_names.append(c.get("name"))

        closure = set()

        def add(name):
            if not name or name in closure or name not in reg.types:
                return
            closure.add(name)
            t = reg.types[name]
            cat = t.get("category")
            if cat in ("struct", "union"):
                for m in t.findall("member"):
                    if api_ok(m):
                        add(member_base(m))
            elif cat == "funcpointer":
                for e in t.findall(".//type"):
                    add(e.text)
            elif cat == "bitmask":
                under = t.find("type")
                if under is not None:
                    add(under.text)

        for n in req_types:
            add(n)
        for cn in cmd_order:
            c = reg.command(cn)
            add(member_base(c.find("proto")))
            for p in c.findall("param"):
                if api_ok(p):
                    add(member_base(p))

        for n in closure:
            cat = reg.category(n)
            if cat == "handle":
                self.handle_set.add(n)
            elif cat == "funcpointer":
                self.fn_set.add(n)
            elif cat == "enum":
                self.enum_type_set.add(n)
            elif cat == "bitmask":
                self.bitmask_set.add(n)
            elif cat == "struct":
                self.struct_set.add(n)
            elif cat == "union":
                self.union_set.add(n)

        # resolve API-constant values first so array sizes can reference them.
        api_consts = []
        block = reg.enum_blocks.get("API Constants")
        if block is not None:
            for e in block.findall("enum"):
                nm = e.get("name")
                if nm in const_seen and not e.get("alias"):
                    ctype = e.get("type")
                    if ctype in ("uint32_t", "int32_t", "uint64_t"):
                        self.const_values[nm] = parse_c_int(e.get("value"))
                    api_consts.append((nm, ctype, e.get("value")))

        return cmd_order, ext_enums, api_consts

    def build(self):
        cmd_order, ext_enums, api_consts = self.collect()
        reg = self.reg
        model = Model()

        for t in reg.root.findall("./types/type"):
            nm = type_id(t)
            if nm in self.handle_set:
                model.handles.append((type_name(nm), nm))
        for t in reg.root.findall("./types/type"):
            nm = type_id(t)
            if nm in self.fn_set:
                model.fns.append(Fn(pfn_name(nm), self.funcpointer_sig(t)))

        for t in reg.root.findall("./types/type"):
            nm = t.get("name")
            if nm in self.struct_set or nm in self.union_set:
                model.records.append(self.build_record(t, nm))

        model.enums = self.build_enums(ext_enums, api_consts)

        for cn in cmd_order:
            model.commands.append(self.build_command(cn))

        return model

    def funcpointer_sig(self, elem):
        args = [self.declarator_type(p, QUAL_TYPES) for p in elem.findall("param")]
        ret = self.declarator_type(elem.find("proto"), QUAL_TYPES)
        sig = "fun({})".format(", ".join(args))
        return sig + (" " + ret if ret else "")

    def build_record(self, elem, cname):
        kind = "rec" if elem.get("category") == "struct" else "uni"
        fields = []
        for m in elem.findall("member"):
            if not api_ok(m):
                continue
            fields.append((ident(m.find("name").text), self.declarator_type(m, QUAL_STRUCTS)))
        return Record(type_name(cname), kind, cname, fields)

    def build_command(self, cn):
        c = self.reg.command(cn)
        ret = self.declarator_type(c.find("proto"), QUAL_C)
        params = []
        for p in c.findall("param"):
            if not api_ok(p):
                continue
            params.append((ident(p.find("name").text), self.declarator_type(p, QUAL_C)))
        return Command(cn, ret, params, self.tier(c))

    def build_enums(self, ext_enums, api_consts):
        reg = self.reg
        groups = {}  # group name -> (kind, bitwidth)

        def register(gname):
            block = reg.enum_blocks.get(gname)
            if block is not None:
                groups[gname] = (block.get("type"), int(block.get("bitwidth") or 32))

        for n in self.enum_type_set:
            register(n)
        for n in self.bitmask_set:
            g = reg.types[n].get("requires") or reg.types[n].get("bitvalues")
            if g:
                register(g)

        raw = {}  # C name -> (group, spec-elem)
        for gname in groups:
            for e in reg.enum_blocks[gname].findall("enum"):
                if e.get("name") and api_ok(e):
                    raw[e.get("name")] = (gname, e)
        for e in ext_enums:
            if e.get("extends") in groups:
                raw[e.get("name")] = (e.get("extends"), e)

        values = {}

        def value_of(c_name, guard=()):
            if c_name in values:
                return values[c_name]
            _, e = raw[c_name]
            if e.get("alias"):
                target = e.get("alias")
                if target in guard or target not in raw:
                    raise KeyError("unresolved enum alias: " + c_name)
                v = value_of(target, guard + (c_name,))
            elif e.get("value") is not None:
                v = parse_c_int(e.get("value"))
            elif e.get("bitpos") is not None:
                v = 1 << int(e.get("bitpos"))
            elif e.get("offset") is not None:
                v = EXT_ENUM_BASE + (int(e.get("extnumber")) - 1) * 1000 + int(e.get("offset"))
                if e.get("dir") == "-":
                    v = -v
            else:
                raise KeyError("enum without a value: " + c_name)
            values[c_name] = v
            return v

        out = []
        for c_name, (gname, _) in raw.items():
            kind, bitwidth = groups[gname]
            v = value_of(c_name)
            if kind == "bitmask":
                width = "u64" if bitwidth == 64 else "u32"
                out.append(Enum(enum_name(c_name), width, hex_literal(v, bitwidth)))
            else:
                out.append(Enum(enum_name(c_name), "i32", str(v)))

        for nm, ctype, val in api_consts:
            width, literal = const_literal(ctype, val)
            out.append(Enum(enum_name(nm), width, literal))

        out.sort(key=lambda e: e.name)
        return out


def hex_literal(v, bitwidth):
    pad = 16 if bitwidth == 64 else 8
    return "0x{:0{}X}".format(v & ((1 << (pad * 4)) - 1), pad)


def const_literal(ctype, val):
    if ctype == "float":
        return "f32", re.sub(r"[fF]$", "", val)
    width = "u64" if ctype == "uint64_t" else "u32"
    n = parse_c_int(val)
    if "~" in val:
        return width, hex_literal(n, 64 if width == "u64" else 32)
    return width, str(n)


HEADER_TYPES = """\
# base handle and function-pointer type aliases for core Vulkan (generated)
#
# opaque handles (dispatchable and non-dispatchable alike) are pointer-sized and
# declared as ptr aliases so a consumer names them by their Vulkan identity; the
# PFN_vk* callback signatures become fun-type aliases. scalar base types
# (VkBool32, VkDeviceSize, VkFlags, ...) and enum/bitmask types resolve straight
# to mach scalars at their use sites and carry no alias here.
#
# GENERATED by tools/gen.py from the pinned tools/vk.xml; do not edit by hand.
"""

HEADER_ENUMS = """\
# core Vulkan enumerant, bitmask, and API constants (generated)
#
# every core enum value with the VK_ prefix stripped. enum constants are i32
# (Vulkan enums are 32-bit signed), bitmask constants are u32 or u64 by the
# registry bitwidth, and API constants keep their declared width. a name that
# would start with a digit gets a leading _.
#
# GENERATED by tools/gen.py from the pinned tools/vk.xml; do not edit by hand.
"""

HEADER_STRUCTS = """\
# core Vulkan structs and unions as C-identical records (generated)
#
# one pub rec per struct and pub uni per union, fields in declaration order with
# their C names preserved. every pNext is a raw ptr; handles, nested records,
# and function pointers reference their vk.types aliases; enums and bitmasks are
# their underlying integers. layout follows the natural C rule, so size and
# offsets match the Vulkan ABI.
#
# GENERATED by tools/gen.py from the pinned tools/vk.xml; do not edit by hand.
"""

HEADER_C = """\
# raw loaded-pointer layer for core Vulkan (generated)
#
# one pub var function pointer per core command, nil until a resolver fills it,
# carrying the C name and a C-faithful signature. a command the running
# implementation does not export stays nil; the same contract as in C.
#
# resolution walks the standard chain: load_global resolves the instanceless
# global commands through the caller's bootstrap vkGetInstanceProcAddr,
# load_instance resolves instance-level commands once an instance exists, and
# load_device narrows device-level commands through vkGetDeviceProcAddr for
# dispatch without the instance trampoline.
#
# GENERATED by tools/gen.py from the pinned tools/vk.xml; do not edit by hand.
"""

HEADER_VK = """\
# the flat public surface of the Vulkan bindings (generated)
#
# re-exports every generated type, handle, enum, struct, and command under one
# namespace so a bare `use vk;` reaches the whole API as vk.load_global(...),
# vk.InstanceCreateInfo{...}, vk.SUCCESS. the raw table stays reachable as
# vk.c.vkCreateInstance for anyone who wants C names.
#
# GENERATED by tools/gen.py from the pinned tools/vk.xml; do not edit by hand.
"""


def field_block(fields):
    if not fields:
        return []
    width = max(len(n) for n, _ in fields)
    return ["    {}: {};".format(n.ljust(width), ty) for n, ty in fields]


def gen_types(model):
    out = [HEADER_TYPES]
    for name, c_name in model.handles:
        out.append("# the {} handle".format(c_name))
        out.append("pub def {}: ptr;".format(name))
    out.append("")
    for fn in model.fns:
        out.append("# the PFN_vk{} callback signature".format(fn.name))
        out.append("pub def {}: {};".format(fn.name, fn.sig))
    out.append("")
    out.append('test "types: a handle is pointer-sized and opaque" {')
    out.append("    if ($size_of(Instance) != 8) { ret 1; }")
    out.append("    if ($size_of(Device) != 8) { ret 1; }")
    out.append("    ret 0;")
    out.append("}")
    return "\n".join(out) + "\n"


def gen_enums(model):
    out = [HEADER_ENUMS]
    for e in model.enums:
        out.append("pub val {}: {} = {};".format(e.name, e.width, e.literal))
    out.append("")
    out.append('test "enums: enum and structure-type values match the registry" {')
    out.append("    if (SUCCESS != 0) { ret 1; }")
    out.append("    if (NOT_READY != 1) { ret 1; }")
    out.append("    if (ERROR_OUT_OF_HOST_MEMORY != -1) { ret 1; }")
    out.append("    if (STRUCTURE_TYPE_APPLICATION_INFO != 0) { ret 1; }")
    out.append("    if (STRUCTURE_TYPE_BIND_BUFFER_MEMORY_INFO != 1000157000) { ret 1; }")
    out.append("    ret 0;")
    out.append("}")
    out.append("")
    out.append('test "enums: bitmask and API constants keep their width" {')
    out.append("    if (QUEUE_GRAPHICS_BIT != 0x00000001) { ret 1; }")
    out.append("    if (QUEUE_COMPUTE_BIT != 0x00000002) { ret 1; }")
    out.append("    if (TRUE != 1) { ret 1; }")
    out.append("    if (FALSE != 0) { ret 1; }")
    out.append("    if (MAX_MEMORY_TYPES != 32) { ret 1; }")
    out.append("    if (WHOLE_SIZE != 0xFFFFFFFFFFFFFFFF) { ret 1; }")
    out.append("    ret 0;")
    out.append("}")
    return "\n".join(out) + "\n"


def gen_structs(model):
    out = [HEADER_STRUCTS, "use vk.types;", ""]
    for r in model.records:
        noun = "structure" if r.kind == "rec" else "union"
        out.append("# the {} {}".format(r.cname, noun))
        out.append("pub {} {} {{".format(r.kind, r.name))
        out.extend(field_block(r.fields))
        out.append("}")
    out.append("")
    out.append('test "structs: record layout matches the Vulkan ABI" {')
    out.append("    if ($offset_of(ApplicationInfo, pNext) != 8) { ret 1; }")
    out.append("    if ($offset_of(ApplicationInfo, apiVersion) != 44) { ret 1; }")
    out.append("    if ($size_of(ApplicationInfo) != 48) { ret 1; }")
    out.append("    ret 0;")
    out.append("}")
    return "\n".join(out) + "\n"


def fun_type(cmd):
    args = ", ".join(ty for _, ty in cmd.params)
    return "fun({})".format(args) + (" " + cmd.ret if cmd.ret else "")


def gen_c(model):
    out = [HEADER_C, "use vk.types;", "use vk.structs;", ""]
    out.append("# resolves a command name against an instance (nil for the global commands),")
    out.append("# returning the entry point or nil. mirrors PFN_vkGetInstanceProcAddr; the")
    out.append("# bootstrap the caller provides")
    out.append("pub def GetInstanceProcAddr: fun(ptr, *u8) ptr;")
    out.append("")
    out.append("# resolves a command name against a device, returning the entry point or nil.")
    out.append("# mirrors PFN_vkGetDeviceProcAddr; the narrowed dispatch path for device-level")
    out.append("# commands")
    out.append("pub def GetDeviceProcAddr: fun(ptr, *u8) ptr;")
    out.append("")
    for cmd in model.commands:
        out.append("# loaded pointer for the {}-level command {}".format(cmd.tier, cmd.name))
        out.append("pub var {}: {} = nil;".format(cmd.name, fun_type(cmd)))
    out.append("")

    tiers = (
        ("global", "load_global", "gipa", "GetInstanceProcAddr", None,
         "resolve the instanceless global commands through the caller's bootstrap "
         "loader, passing a nil instance"),
        ("instance", "load_instance", "gipa", "GetInstanceProcAddr", "instance",
         "resolve the instance-level commands through the caller's bootstrap loader "
         "against a created instance"),
        ("device", "load_device", "gdpa", "GetDeviceProcAddr", "device",
         "resolve the device-level commands through vkGetDeviceProcAddr, skipping the "
         "instance dispatch trampoline"),
    )
    for tier, fname, loader, loader_ty, handle, doc in tiers:
        cmds = [c for c in model.commands if c.tier == tier]
        loader_doc = "bootstrap vkGetInstanceProcAddr" if loader == "gipa" else "device's vkGetDeviceProcAddr"
        comps = [(loader, "the " + loader_doc)]
        if handle:
            comps.append((handle, "the created {} to resolve against".format(handle)))
        comps.append(("ret", "the number of {} commands resolved; unresolved pointers stay nil".format(tier)))
        cw = max(len(cid) for cid, _ in comps)
        out.append("# {}".format(doc))
        out.append("# ---")
        for cid, cdesc in comps:
            out.append("# {}: {}".format(cid.ljust(cw), cdesc))
        if handle:
            out.append("pub fun {}({}: {}, {}: ptr) i64 {{".format(fname, loader, loader_ty, handle))
        else:
            out.append("pub fun {}({}: {}) i64 {{".format(fname, loader, loader_ty))
        dispatch = handle if handle else "nil"
        out.append("    var n: i64 = 0;")
        for cmd in cmds:
            sig = fun_type(cmd)
            out.append('    {} = {}({}, "{}"):~{};'.format(cmd.name, loader, dispatch, cmd.name, sig))
            out.append("    if ({} != nil) {{ n = n + 1; }}".format(cmd.name))
        out.append("    ret n;")
        out.append("}")
        out.append("")

    out.extend(gen_c_tests())
    return "\n".join(out) + "\n"


def gen_c_tests():
    return [
        "fun gipa_nil(instance: ptr, name: *u8) ptr {",
        "    ret nil;",
        "}",
        "",
        "var load_calls: i64 = 0;",
        "",
        "fun gipa_count(instance: ptr, name: *u8) ptr {",
        "    load_calls = load_calls + 1;",
        "    ret (?load_calls)::ptr;",
        "}",
        "",
        "fun gdpa_count(device: ptr, name: *u8) ptr {",
        "    load_calls = load_calls + 1;",
        "    ret (?load_calls)::ptr;",
        "}",
        "",
        "# a nil loader resolves nothing and leaves the global table nil",
        'test "c: load_global with a nil loader resolves nothing" {',
        "    val n: i64 = load_global(gipa_nil);",
        "    if (n != 0) { ret 1; }",
        "    if (vkCreateInstance != nil) { ret 1; }",
        "    ret 0;",
        "}",
        "",
        "# a stub loader that answers every name resolves each tier fully; the count",
        "# equals the number of loader calls for that tier",
        'test "c: a stub loader resolves every command in each tier" {',
        "    load_calls = 0;",
        "    val g: i64 = load_global(gipa_count);",
        "    if (g != load_calls) { ret 1; }",
        "    if (g <= 0) { ret 1; }",
        "    load_calls = 0;",
        "    val i: i64 = load_instance(gipa_count, (?load_calls)::ptr);",
        "    if (i != load_calls) { ret 1; }",
        "    if (i <= 0) { ret 1; }",
        "    load_calls = 0;",
        "    val d: i64 = load_device(gdpa_count, (?load_calls)::ptr);",
        "    if (d != load_calls) { ret 1; }",
        "    if (d <= 0) { ret 1; }",
        "    ret 0;",
        "}",
        "",
        "var abi_seen: u32 = 0;",
        "",
        "fun abi_fake(api: *u32) i32 {",
        "    @api = abi_seen;",
        "    ret 0;",
        "}",
        "",
        "# pin the loaded-pointer call ABI: a mach fake stands in for a command and the",
        "# call must deliver the out-pointer and read its result back without a loader",
        'test "c: loaded-pointer call ABI" {',
        "    abi_seen = 0x00403000;",
        "    vkEnumerateInstanceVersion = abi_fake;",
        "    var ver: u32 = 0;",
        "    val r: i32 = vkEnumerateInstanceVersion(?ver);",
        "    if (r != 0) { ret 1; }",
        "    if (ver != 0x00403000) { ret 1; }",
        "    ret 0;",
        "}",
    ]


def gen_vk(model):
    out = [HEADER_VK]
    out.append("use vk.types;")
    out.append("use vk.enums;")
    out.append("use vk.structs;")
    out.append("# links the startup entrypoint so `mach test` over this library produces a binary")
    out.append("use std.runtime;")
    out.append("")
    out.append("fwd vk.c;")
    out.append("fwd vk.c.GetInstanceProcAddr;")
    out.append("fwd vk.c.GetDeviceProcAddr;")
    out.append("fwd vk.c.load_global;")
    out.append("fwd vk.c.load_instance;")
    out.append("fwd vk.c.load_device;")
    for cmd in model.commands:
        out.append("fwd vk.c.{};".format(cmd.name))
    for name, _ in model.handles:
        out.append("fwd types.{};".format(name))
    for fn in model.fns:
        out.append("fwd types.{};".format(fn.name))
    for e in model.enums:
        out.append("fwd enums.{};".format(e.name))
    for r in model.records:
        out.append("fwd structs.{};".format(r.name))
    return "\n".join(out) + "\n"


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

    reg = Registry(XML)
    model = Generator(reg).build()
    files = render(model)

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
    sys.stderr.write(
        "generated {} handles, {} fn typedefs, {} records, {} enums, {} commands\n".format(
            len(model.handles), len(model.fns), len(model.records),
            len(model.enums), len(model.commands),
        )
    )


if __name__ == "__main__":
    main()

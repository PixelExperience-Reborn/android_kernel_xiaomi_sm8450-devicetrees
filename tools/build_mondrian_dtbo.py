#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the mondrian dtbo.img: one overlay, as the stock OS3.0.8.0 dtbo has.

The DT chain of this repository applies nine overlays one after another
(board, Camera platform and routes, display, audio, video, audio board,
MMRM). The bootloader applies one dtbo entry. This tool joins the
preprocessed sources of the nine overlays, in the same order, into one
overlay source, so dtc links references between them at compile time, as
Qualcomm and Xiaomi build their dtbo. The root of the result carries only
the mondrian board identity.

The result is accepted only if, applied to each Cape base DTB, it gives
the same tree as the chain: every node and property, with phandles
compared by the node they point to. Then dtbo.img (Android DTBO v0, one
entry) and the base DTBs for vendor_boot are written with their sha256.
"""
import argparse
import hashlib
import json
import re
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASES = ("cape", "capep", "cape-v2")
SOURCES = (
    ("board", "mondrian-sm8475-pm8008-overlay.preprocessed.dts"),
    ("camera", "mondrian-camera-platform.preprocessed.dts"),
    ("camera", "mondrian-camera-board.preprocessed.dts"),
    ("m11a", "cape-sde.preprocessed.dts"),
    ("m11a", "mondrian-m11a-primary.preprocessed.dts"),
    ("multimedia", "cape-audio.preprocessed.dts"),
    ("multimedia", "waipio-vidc.preprocessed.dts"),
    ("multimedia", "mondrian-audio-board.preprocessed.dts"),
    ("multimedia", "mondrian-mmrm.preprocessed.dts"),
)
IDENTITY = ("model", "compatible", "qcom,msm-id", "qcom,board-id", "xiaomi,miboard-id")
DTBO_MAGIC = 0xD7B7AB1E
PAGE_SIZE = 4096


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def strip_source(text):
    out = []
    for line in text.splitlines():
        if re.match(r'^# \d+ "', line):
            continue
        line = line.replace("/dts-v1/;", "").replace("/plugin/;", "")
        out.append(line)
    return "\n".join(out) + "\n"


def fdt_nodes(path):
    """{node path: {property: bytes}} of a flattened device tree."""
    data = Path(path).read_bytes()
    magic, _total, off_struct, off_strings = struct.unpack(">4I", data[:16])
    if magic != 0xD00DFEED:
        raise ValueError(f"{path}: not a flattened device tree")
    strings = data[off_strings:]
    nodes, stack, p = {}, [], off_struct
    while True:
        token = struct.unpack(">I", data[p:p + 4])[0]
        p += 4
        if token == 1:
            end = data.index(b"\0", p)
            stack.append(data[p:end].decode())
            p = (end + 4) & ~3
            nodes["/" + "/".join(stack[1:])] = {}
        elif token == 2:
            stack.pop()
        elif token == 3:
            length, nameoff = struct.unpack(">II", data[p:p + 8])
            p += 8
            name = strings[nameoff:strings.index(b"\0", nameoff)].decode()
            nodes["/" + "/".join(stack[1:])][name] = data[p:p + length]
            p = (p + length + 3) & ~3
        elif token == 9:
            return nodes


def resolved_tree(path):
    """Nodes and properties with every cell that is a phandle shown as both
    its number and the node it points to, so that two trees can be compared
    independently of phandle numbering."""
    nodes = {k: v for k, v in fdt_nodes(path).items()
             if not k.startswith(("/__symbols__", "/__fixups__", "/__local_fixups__"))}
    handles = {struct.unpack(">I", v["phandle"])[0]: p for p, v in nodes.items() if "phandle" in v}
    out = {}
    for node, props in nodes.items():
        for name, value in props.items():
            if name in ("phandle", "linux,phandle"):
                continue
            out[node, name] = value
    return out, handles


def same_tree(a, b):
    (ta, ha), (tb, hb) = resolved_tree(a), resolved_tree(b)
    differences = []
    for key in sorted(set(ta) | set(tb)):
        va, vb = ta.get(key), tb.get(key)
        if va == vb:
            continue
        if va is not None and vb is not None and len(va) == len(vb) and len(va) % 4 == 0:
            ca = struct.unpack(">%dI" % (len(va) // 4), va)
            cb = struct.unpack(">%dI" % (len(vb) // 4), vb)
            if all(x == y or (x in ha and y in hb and ha[x] == hb[y]) for x, y in zip(ca, cb)):
                continue
        differences.append(f"{key[0]} {key[1]}")
    return differences


def dts_value(raw):
    if raw and raw.endswith(b"\0") and all(32 <= c < 127 or c == 0 for c in raw):
        return ", ".join('"%s"' % s for s in raw[:-1].decode().split("\0"))
    cells = struct.unpack(">%dI" % (len(raw) // 4), raw)
    return "<" + " ".join("0x%x" % c for c in cells) + ">"


def dtbo_image(overlay, path):
    blob = Path(overlay).read_bytes()
    header_size, entry_size = 32, 32
    offset = header_size + entry_size
    total = offset + len(blob)
    header = struct.pack(">8I", DTBO_MAGIC, total, header_size, entry_size, 1,
                         header_size, PAGE_SIZE, 0)
    entry = struct.pack(">8I", len(blob), offset, 0, 0, 0, 0, 0, 0)
    Path(path).write_bytes(header + entry + blob)


def build(builds, out):
    out.mkdir(parents=True, exist_ok=True)
    board_overlay = builds["board"] / "images/mondrian-sm8475-pm8008-overlay.dtbo"
    identity = fdt_nodes(board_overlay)["/"]
    parts = ["/dts-v1/;\n/plugin/;\n"]
    for stage, name in SOURCES:
        source = builds[stage] / name
        parts.append(f"\n/* ---- {stage}/{name} ---- */\n")
        parts.append(strip_source(source.read_text()))
    parts.append("\n/* ---- mondrian board identity (the board overlay root) ---- */\n/ {\n")
    for prop in IDENTITY:
        if prop in identity:
            parts.append(f"\t{prop} = {dts_value(identity[prop])};\n")
    parts.append("};\n")
    combined = out / "mondrian-overlay.dts"
    combined.write_text("".join(parts))
    overlay = out / "mondrian.dtbo"
    run(["dtc", "-q", "-@", "-I", "dts", "-O", "dtb", "-o", overlay, combined])

    root = fdt_nodes(overlay)["/"]
    extra = sorted(set(root) - set(identity) - {"phandle"})
    if extra or any(root.get(p) != identity.get(p) for p in IDENTITY):
        raise ValueError(f"overlay root differs from the mondrian board identity: {extra}")

    report = {"overlay_sha256": sha256(overlay), "boards": {}}
    for base in BASES:
        base_dtb = builds["board"] / "images" / (base + ".dtb")
        chain = builds["multimedia"] / (base + "-mondrian-full.dtb")
        applied = out / (base + "-mondrian-dtbo-applied.dtb")
        run(["fdtoverlay", "-i", base_dtb, "-o", applied, overlay])
        differences = same_tree(applied, chain)
        if differences:
            raise ValueError(f"{base}: one overlay does not give the chain's tree: {differences[:20]}")
        report["boards"][base] = {"base_sha256": sha256(base_dtb), "chain_sha256": sha256(chain),
                                  "applied_equals_chain": True}
        (out / "dtbs").mkdir(exist_ok=True)
        (out / "dtbs" / (base + ".dtb")).write_bytes(base_dtb.read_bytes())
    dtbo_image(overlay, out / "dtbo.img")
    report["dtbo_img_sha256"] = sha256(out / "dtbo.img")
    report["dtbs_sha256"] = {b: sha256(out / "dtbs" / (b + ".dtb")) for b in BASES}
    (out / "mondrian-dtbo-build.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for stage in ("board", "camera", "m11a", "multimedia"):
        parser.add_argument(f"--{stage}-build", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    builds = {s: getattr(args, s + "_build").resolve() for s in ("board", "camera", "m11a", "multimedia")}
    try:
        report = build(builds, args.out.resolve())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1
    print(f"[PASS] one mondrian overlay gives the chain's tree on {', '.join(report['boards'])}; "
          f"dtbo.img {report['dtbo_img_sha256'][:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

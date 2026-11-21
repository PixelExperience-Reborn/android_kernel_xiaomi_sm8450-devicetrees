#!/usr/bin/env python3
"""Build Xiaomi's M11A display on the three camera-integrated mondrian DTBs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
from tempfile import TemporaryDirectory

from build_oem_dtbo import BASES, ROOT, run, verify_kernel_revision


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compile_overlay(source, dest, kernel, display, temp):
    preprocessed = temp / (source.stem + ".dts")
    with preprocessed.open("wb") as stream:
        run(["cpp", "-nostdinc", "-undef", "-D__DTS__", "-x", "assembler-with-cpp",
             "-I", kernel / "include", "-I", display, source], stdout=stream)
    run(["dtc", "-q", "-@", "-I", "dts", "-O", "dtb", "-o", dest, preprocessed])


def command_packets(data):
    """Read the Qualcomm 7-byte DSI packet headers used by the M11A DTS."""
    packets = []
    offset = 0
    while offset < len(data):
        if len(data) - offset < 7:
            raise ValueError(f"incomplete DSI header at byte {offset}")
        size = int.from_bytes(data[offset + 5:offset + 7], "big")
        end = offset + 7 + size
        if not size or end > len(data):
            raise ValueError(f"invalid M11A DSI payload length {size} at byte {offset}")
        packets.append((data[offset + 4], data[offset + 7:end]))
        offset = end
    return packets


def byte_property(dtb, node, name):
    # fdtget's byte output has no leading zero for single-digit hex values.
    raw = subprocess.check_output(["fdtget", "-t", "bx", dtb, node, name], text=True)
    return bytes(int(value, 16) for value in raw.split())


def verify_lhbm_updates(dtb, mode):
    properties = subprocess.check_output(["fdtget", "-p", dtb, mode], text=True).splitlines()
    required = {"normal-white-1000nit", "normal-white-110nit", "normal-green-500nit",
                "off-to-normal", "off-to-hbm", "hlpm-white-1000nit", "hlpm-white-110nit"}
    prefix = "mi,mdss-dsi-local-hbm-"
    for prop in properties:
        if not prop.startswith(prefix) or not prop.endswith("-command-update"):
            continue
        commands = command_packets(byte_property(dtb, mode, prop.removesuffix("-update")))
        updates = byte_property(dtb, mode, prop)
        if not updates or len(updates) % 12:
            raise ValueError(f"{mode}: invalid update table for {prop}")
        for register, index, size in struct.iter_unpack(">III", updates):
            if index >= len(commands):
                raise ValueError(f"{mode}: {prop} references missing packet {index}")
            payload = commands[index][1]
            if payload[0] != register or not 0 < size < len(payload):
                raise ValueError(f"{mode}: {prop} does not fit packet {index}")
        required.discard(prop[len(prefix):-len("-command-update")])
    if required:
        raise ValueError(f"{mode}: missing local HBM update tables {sorted(required)}")


def verify_panel(dtb):
    def read(path, key, fmt="x"):
        return subprocess.check_output(["fdtget", "-t", fmt, dtb, path, key], text=True).strip()

    def symbol(name):
        return read("/__symbols__", name, "s")

    primary = symbol("sde_dsi")
    panel = symbol("dsi_m11a_42_02_0a_dsc_cmd")
    supplies = symbol("dsi_panel_pwr_supply_M11a")
    if (read(primary, "qcom,dsi-default-panel") != read(panel, "phandle") or
            read(panel, "qcom,panel-supply-entries") != read(supplies, "phandle") or
            read(panel, "mi,panel-id") != "4d313141 420200"):
        raise ValueError(f"{dtb.name}: primary display or supply mapping does not match M11A")
    ready_frames = int(read(panel, "mi,local-hbm-ui-ready-delay-num-frame"), 16)
    if ready_frames != 4:
        raise ValueError(f"{dtb.name}: unexpected M11A FOD readiness delay")
    on_counts = {}
    timings = panel + "/qcom,mdss-dsi-display-timings"
    for name in subprocess.check_output(["fdtget", "-l", dtb, timings], text=True).splitlines():
        node = timings + "/" + name
        width, height, slice_w, slice_h, rate = (
            int(read(node, prop), 16) for prop in (
                "qcom,mdss-dsi-panel-width", "qcom,mdss-dsi-panel-height",
                "qcom,mdss-dsc-slice-width", "qcom,mdss-dsc-slice-height",
                "qcom,mdss-dsi-panel-framerate"))
        if (width, height, slice_w, slice_h) != (1440, 3200, 720, 32) or read(
                node, "qcom,compression-mode", "s") != "dsc":
            raise ValueError(f"{dtb.name}: unexpected M11A mode {name}")
        on = command_packets(byte_property(dtb, node, "qcom,mdss-dsi-on-command"))
        power_on = [(payload[0], delay) for delay, payload in on if payload[0] in (0x11, 0x29)]
        if power_on != [(0x11, 120), (0x29, 0)] or rate in on_counts:
            raise ValueError(f"{dtb.name}: invalid M11A initialization for {rate} Hz")
        verify_lhbm_updates(dtb, node)
        on_counts[rate] = len(on)
    if sorted(on_counts) != [60, 90, 120]:
        raise ValueError(f"{dtb.name}: unexpected M11A refresh rates {sorted(on_counts)}")
    return {"panel": panel, "refresh_hz": sorted(on_counts), "panel_on_packets": on_counts,
            "fod_ready_delay_frames": ready_frames, "sha256": digest(dtb)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path, required=True)
    parser.add_argument("--camera-build", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    camera = json.loads((args.camera_build / "mondrian-camera-platform-diagnostic-evidence.json").read_text())
    sources = json.loads((ROOT / "oem-m11a-panel-source-lock.json").read_text())
    kernel_sha = verify_kernel_revision(args.kernel, sources["display_source"]["kernel_commit"])
    if camera["kernel_commit"] != kernel_sha or camera["device"] != "mondrian":
        raise ValueError("camera board and display kernel revisions do not match")
    upstream = ROOT / "upstream/xiaomi-display"
    display_sha = subprocess.check_output(["git", "-C", upstream, "rev-parse", "HEAD"], text=True).strip()
    if display_sha != sources["display_source"]["commit"]:
        raise ValueError("unexpected Xiaomi display source revision")
    args.out.mkdir(parents=True, exist_ok=True)
    results = {}
    with TemporaryDirectory(dir=args.out) as directory:
        temp = Path(directory)
        display = temp / "display"
        shutil.copytree(upstream / "display", display)
        for patch in ("mondrian-m11a-panel-on-90hz.patch", "mondrian-m11a-lhbm-commands.patch"):
            subprocess.run(["patch", "--batch", "--forward", "--fuzz=0", "-s", "-p1",
                            "-i", ROOT / "patches" / patch], cwd=temp, check=True)
        cape = temp / "cape-sde.dtbo"
        board = temp / "mondrian-m11a-primary.dtbo"
        compile_overlay(display / "cape-sde.dts", cape, args.kernel, display, temp)
        compile_overlay(ROOT / "qcom/mondrian-m11a-primary-overlay.dts", board, args.kernel, display, temp)
        for name in BASES:
            base = args.camera_build / "images" / (name + "-mondrian-camera-board-diagnostic.dtb")
            if digest(base) != camera["per_board"][name]["camera_board_merged_sha256"]:
                raise ValueError(f"{name}: camera board hash mismatch")
            merged = temp / (name + "-mondrian-m11a.dtb")
            run(["fdtoverlay", "-i", base, "-o", merged, cape, board])
            results[name] = verify_panel(merged)
        for binary in (cape, board, *(temp / (name + "-mondrian-m11a.dtb") for name in BASES)):
            binary.replace(args.out / binary.name)
    report = {"kernel_commit": kernel_sha, "xiaomi_display_commit": display_sha,
              "boards": results, "hardware_verified": False, "production_dtbo_approved": False}
    (args.out / "mondrian-m11a-build.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Compiled and linked M11A on " + ", ".join(results))


if __name__ == "__main__":
    main()

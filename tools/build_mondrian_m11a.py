#!/usr/bin/env python3
"""Build Xiaomi's M11A display on the three camera-integrated mondrian DTBs."""
import argparse
import hashlib
import json
from pathlib import Path
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
    rates = []
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
        rates.append(rate)
    if sorted(rates) != [60, 90, 120]:
        raise ValueError(f"{dtb.name}: unexpected M11A refresh rates {rates}")
    return {"panel": panel, "refresh_hz": sorted(rates), "sha256": digest(dtb)}


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
    display = upstream / "display"
    args.out.mkdir(parents=True, exist_ok=True)
    results = {}
    with TemporaryDirectory(dir=args.out) as directory:
        temp = Path(directory)
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

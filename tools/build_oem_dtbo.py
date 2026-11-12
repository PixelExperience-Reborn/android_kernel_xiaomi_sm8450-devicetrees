#!/usr/bin/env python3
"""Compile Xiaomi mondrian DTB/DTBO against a selected PE-Reborn OEM kernel."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASES = ("cape", "cape-v2", "capep")
BOARD = "mondrian-sm8475-pm8008-overlay"

def run(args, *, stdout=None):
    print("+", " ".join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), check=True, stdout=stdout)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--kernel", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--oem", type=Path, default=ROOT / "upstream/xiaomi-dts")
    args = parser.parse_args()
    kernel = args.kernel.resolve()
    oem = args.oem.resolve()
    out = args.out.resolve()
    lock = json.loads((ROOT / "oem-source-lock.json").read_text())
    if not (kernel / "Makefile").is_file() or not (oem / "qcom/cape.dts").is_file():
        parser.error("Kernel source and pinned Xiaomi DT submodule are required")
    oem_head = subprocess.check_output(["git", "-C", str(oem), "rev-parse", "HEAD"], text=True).strip()
    if oem_head != lock["source_commit"]:
        parser.error(f"Xiaomi source SHA mismatch: {oem_head}")
    kernel_head = subprocess.check_output(
        ["git", "-C", str(kernel), "rev-parse", "HEAD"], text=True
    ).strip()
    if kernel_head != lock["selected_kernel_commit"]:
        parser.error(f"Kernel commit mismatch: {kernel_head}")
    for tool in ("cpp", "dtc", "fdtoverlay", "fdtget"):
        if not shutil.which(tool):
            parser.error(f"Required tool is missing: {tool}")
    stage = out / "source"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    shutil.copytree(oem / "qcom", stage / "qcom")
    for rel in lock["original_git_blobs"]:
        source = ROOT / rel
        dest = stage / rel
        if not source.is_file() or not dest.is_file():
            parser.error(f"Missing pinned source: {rel}")
        shutil.copy2(source, dest)
    include_dirs = (kernel / "include", kernel / "arch/arm64/boot/dts",
                    stage, stage / "qcom")
    dest = out / "images"
    dest.mkdir(parents=True, exist_ok=True)

    def compile_one(name, overlay):
        src = stage / "qcom" / (name + ".dts")
        if not src.is_file():
            raise FileNotFoundError(src)
        preprocessed = out / (name + ".preprocessed.dts")
        cmd = ["cpp", "-nostdinc", "-undef", "-D__DTS__", "-x", "assembler-with-cpp"]
        for directory in include_dirs:
            cmd.extend(["-I", directory])
        cmd.append(src)
        with preprocessed.open("wb") as output:
            run(cmd, stdout=output)
        result = dest / (name + (".dtbo" if overlay else ".dtb"))
        run(["dtc", "-@", "-I", "dts", "-O", "dtb", "-o", result, preprocessed])
        if result.stat().st_size < 100:
            raise RuntimeError(f"Invalid DT binary: {result}")
        return result

    bases = [compile_one(name, False) for name in BASES]
    overlay = compile_one(BOARD, True)
    overlay_model = subprocess.check_output(
        ["fdtget", "-t", "s", str(overlay), "/", "model"], text=True
    ).strip()
    if "Mondrian" not in overlay_model or "SM8475" not in overlay_model:
        raise RuntimeError(f"Incorrect board overlay identity: {overlay_model}")
    board_id = subprocess.check_output(
        ["fdtget", "-t", "x", str(overlay), "/", "xiaomi,miboard-id"],
        text=True
    ).strip()
    if [int(x, 16) for x in board_id.split()] != [0xE, 0]:
        raise RuntimeError(f"Unexpected mondrian miboard-id: {board_id}")
    for base in bases:
        merged = dest / (base.stem + "-mondrian-merged.dtb")
        run(["fdtoverlay", "-i", base, "-o", merged, overlay])
        if not merged.is_file() or merged.stat().st_size < base.stat().st_size:
            raise RuntimeError(f"Invalid merged DTB: {merged}")
        model = subprocess.check_output(
            ["fdtget", "-t", "s", str(merged), "/", "model"], text=True
        ).strip()
        # Overlay root metadata is for bootloader selection and is not
        # automatically copied over the root 'model' of a Cape base DTB.
        if "Cape" not in model:
            raise RuntimeError(f"Wrong base board used in merged DTB: {model}")
        expanded = out / (base.stem + "-mondrian-merged.dts")
        run(["dtc", "-I", "dtb", "-O", "dts", "-o", expanded, merged])
        dt = expanded.read_text()
        # Verify OEM QCA6490 CNSS/PCIe DTS alongside the independently
        # compiled Xiaomi QCACLD kernel module. This does not attest RF,
        # vendor firmware, Bluetooth coexistence, or hardware power-on.
        required = (
            'goodix,gt9916S',
            'goodix_firmware_m11a.bin',
            'goodix_cfg_group_m11a.bin',
            'qcom,cnss-qca6490',
            'wlan-en-gpio',
            'qcom,bt-en-gpio',
            'qcom,sw-ctrl-gpio',
            'qcom,wlan-rc-num',
            'vdd-wlan-aon-supply',
            'vdd-wlan-dig-supply',
            'vdd-wlan-io-supply',
            'vdd-wlan-rfa1-supply',
            'vdd-wlan-rfa2-supply',
            'wlan-ant-switch-supply',
            'qcom,wlan-ramdump-dynamic',
        )
        for name in required:
            if name not in dt:
                raise RuntimeError(f"Missing {name} in merged {base.stem}")
        if dt.count('compatible = "qcom,cnss-qca6490";') != 1:
            raise RuntimeError(f"Expected exactly one QCA6490 CNSS node in {base.stem}")
    result_files = sorted(dest.glob("*.dtb")) + sorted(dest.glob("*.dtbo"))
    provenance = {
        "device": "mondrian",
        "kernel": kernel_head,
        "oem_device_tree": oem_head,
        "model": "SM8475",
        "outputs_sha256": {
            f.name: hashlib.sha256(f.read_bytes()).hexdigest()
            for f in result_files
        },
        "board_overlay_applied_to_all_cape_bases": True,
        "qca6490_oem_cnss_and_regulator_contract_verified": True,
        "qca6490_hardware_rf_and_firmware_verified": False,
        "display_camera_overlays_compiled": False,
        "bootloader_hardware_verified": False,
        "android17_boot_verified": False,
    }
    (out / "dtbo-diagnostic-evidence.json").write_text(
        json.dumps(provenance, indent=2) + "\n"
    )
    print("[PASS] OEM Cape DTBs and mondrian board overlay compiled and applied")
    print("[PENDING] Display/camera DTBO, bootloader and hardware boot")

if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.CalledProcessError, RuntimeError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        sys.exit(1)

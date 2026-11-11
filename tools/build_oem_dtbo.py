#!/usr/bin/env python3
"""Compile Xiaomi mondrian DTB/DTBO against a selected PE-Reborn OEM kernel."""
import argparse
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
    for tool in ("cpp", "dtc", "fdtoverlay"):
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
    for base in bases:
        merged = dest / (base.stem + "-mondrian-merged.dtb")
        run(["fdtoverlay", "-i", base, "-o", merged, overlay])
        if not merged.is_file() or merged.stat().st_size < base.stat().st_size:
            raise RuntimeError(f"Invalid merged DTB: {merged}")
    print("[PASS] OEM Cape DTBs and mondrian board overlay compiled and applied")
    print("[PENDING] Display/camera DTBO, bootloader and hardware boot")

if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.CalledProcessError, RuntimeError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        sys.exit(1)

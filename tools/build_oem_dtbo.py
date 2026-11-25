#!/usr/bin/env python3
"""Compile Xiaomi mondrian DTB/DTBO against a selected PE-Reborn OEM kernel."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from verify_mondrian_camera_pmic_fdt import verify_mondrian_camera_pmic_fdt
from verify_mondrian_audio_fdt import verify_mondrian_audio_fdt
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASES = ("cape", "cape-v2", "capep")
BOARD = "mondrian-sm8475-pm8008-overlay"


def verify_kernel_revision(kernel, expected):
    """Ensure compiled board evidence is tied to one real Git commit."""
    if re.fullmatch(r"[0-9a-f]{40}", expected) is None:
        raise ValueError("Expected kernel revision must be a lowercase 40-hex SHA")
    actual = subprocess.check_output(
        ["git", "-C", str(kernel), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual != expected:
        raise ValueError(f"Kernel commit mismatch: expected {expected}, got {actual}")
    return actual

def run(args, *, stdout=None):
    print("+", " ".join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), check=True, stdout=stdout)



def canonicalize_generated_overlay_fdt(merged, canonical):
    """Round-trip only a disposable *compiled* FDT for strict PMIC inspection.

    fdtoverlay/libfdt output can carry nonzero property alignment bytes; the
    exact original merged image must remain untouched. Never weaken the
    stock-firmware FDT parser. Re-emit a temporary standard dtc DTB and
    require identical complete DTS on both sides before trusting the copy.
    """
    merged, canonical = Path(merged), Path(canonical)
    if not merged.is_file() or merged.stat().st_size < 100:
        raise RuntimeError("missing or truncated original merged OEM DTB")
    if canonical.exists() or canonical.is_symlink():
        raise RuntimeError("refusing to overwrite an existing canonical DTB")
    run(["dtc", "-I", "dtb", "-O", "dtb", "-o", canonical, merged])
    if not canonical.is_file() or canonical.stat().st_size < 100:
        raise RuntimeError("dtc failed to produce a canonical OEM DTB")
    raw_dts = subprocess.check_output(
        ["dtc", "-I", "dtb", "-O", "dts", str(merged)])
    roundtrip_dts = subprocess.check_output(
        ["dtc", "-I", "dtb", "-O", "dts", str(canonical)])
    if raw_dts != roundtrip_dts:
        raise RuntimeError("compiled FDT canonicalization changed OEM DT semantics")
    return {
        "original_merged_dtb_sha256": hashlib.sha256(
            merged.read_bytes()).hexdigest(),
        "inspection_only_canonical_dtb_sha256": hashlib.sha256(
            canonical.read_bytes()).hexdigest(),
        "complete_original_and_canonical_dts_identical": True,
        "canonical_copy_used_only_for_static_pmic_inspection": True,
        "original_merged_dtb_not_replaced": True,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--kernel", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--oem", type=Path, default=ROOT / "upstream/xiaomi-dts")
    parser.add_argument("--expected-kernel-commit",
                        help="Exact selected kernel SHA; defaults to OEM-only source lock")
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
    try:
        kernel_head = verify_kernel_revision(
            kernel, args.expected_kernel_commit or lock["selected_kernel_commit"])
    except ValueError as exc:
        parser.error(str(exc))
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
    camera_pmic_evidence = {}
    audio_board_evidence = {}
    for base in bases:
        merged = dest / (base.stem + "-mondrian-merged.dtb")
        run(["fdtoverlay", "-i", base, "-o", merged, overlay])
        if not merged.is_file() or merged.stat().st_size < base.stat().st_size:
            raise RuntimeError(f"Invalid merged DTB: {merged}")
        model = subprocess.check_output(
            ["fdtget", "-t", "s", str(merged), "/", "model"], text=True
        ).strip()
        # Check the original merged image with libfdt before normalizing a
        # separate inspection-only copy. Never alter the build's DTB output.
        if "Cape" not in model:
            raise RuntimeError(f"Wrong base board used in merged DTB: {model}")
        with TemporaryDirectory(prefix="pe-mondrian-pmic-", dir=out) as temp:
            canonical = Path(temp) / "inspected-oem.dtb"
            roundtrip_evidence = canonicalize_generated_overlay_fdt(
                merged, canonical)
            compiled_fdt = canonical.read_bytes()
            pmic = verify_mondrian_camera_pmic_fdt(compiled_fdt)
            audio = verify_mondrian_audio_fdt(compiled_fdt)
            pmic.update(roundtrip_evidence)
            audio.update(roundtrip_evidence)
            camera_pmic_evidence[base.stem] = pmic
            audio_board_evidence[base.stem] = audio
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
            'goodix,fingerprint',
            'goodix,gpio-reset',
            'goodix,gpio-irq',
            'l1c_vdd-supply',
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
        "goodix_udfps_oem_bindings_verified": True,
        "goodix_udfps_device_runtime_verified": False,
        "camera_pmic_oem_source_links_compiled": True,
        "camera_pmic_compiled_evidence": camera_pmic_evidence,
        "mondrian_oem_audio_speaker_source_compiled": True,
        "mondrian_oem_audio_compiled_evidence": audio_board_evidence,
        "mondrian_audio_kernel_abi_qualified": False,
        "mondrian_audio_hal_qualified": False,
        "mondrian_audio_hardware_verified": False,
        "production_audio_approved": False,
        "mondrian_camera_flash_consumer_qualified": False,
        "mondrian_camera_sensor_power_cci_qualified": False,
        "display_camera_overlays_compiled": False,
        "bootloader_hardware_verified": False,
        "android17_boot_verified": False,
    }
    (out / "dtbo-diagnostic-evidence.json").write_text(
        json.dumps(provenance, indent=2) + "\n"
    )
    print("[PASS] OEM Cape DTBs and mondrian board overlay compiled and applied")
    print("[PASS] OEM mondrian AW882xx I2C/GPIO and MI2S2 board routing in all Cape DTBs")
    print("[PENDING] Display/camera DTBO, bootloader and hardware boot")

if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.CalledProcessError, RuntimeError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        sys.exit(1)

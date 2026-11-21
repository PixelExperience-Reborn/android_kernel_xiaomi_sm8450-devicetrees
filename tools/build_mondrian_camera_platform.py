#!/usr/bin/env python3
"""Build the Cape camera controllers and the mondrian diagnostic board overlay.

Keep MiCode source unmodified; use existing OEM Cape+mondrian board DTBs and
the exact pinned Xiaomi Camera kernel dt-binding header. Apply the Camera
overlay ONLY to diagnostic copies. Disallow any alteration of existing base
DTB property bytes in the controller stage. The separate board stage restores
the mondrian sensor routes, shared supplies and the board-specific flash channel.

This is a static build/ABI gate, not a flashable or bootloader-selected DTBO.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory

from audit_xiaomi_panel_evidence import fdt_nodes
from build_oem_dtbo import (
    BASES, BOARD, canonicalize_generated_overlay_fdt, run,
    verify_kernel_revision,
)

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "qcom/mondrian-sm8475-camera-platform-overlay.dts"
BOARD_CAMERA = ROOT / "qcom/mondrian-sm8475-camera-board-overlay.dts"
HAL_PROFILES = ROOT / "mondrian-camera-hal-profiles.json"
CAMERA_PLATFORM_SHA = "a59a63bd498b94074c41357a466874b99aec62a8"
CAMERA_PLATFORM_TREE = "dcd9bc5855358af4a3c39a9a582472d3190766cc"
CAMERA_KERNEL_SHA = "9ed4ce96d49c0759c6365627113c5f59c2407942"
CAMERA_HEADER_SHA = "9bdc2b4c0257cdb18626d46cfb691df845202b48"
KERNEL_SHA = "6b1293a9c03b2cf814878d6565ee17e33afe84f4"
EXPECTED_IMPORT = '#include "cape-camera.dtsi"'
MONDRIAN_M11A_PHY_IDS = (2, 4)
M11A_COMPATIBLE = b"qcom,csiphy-v2.1.3-xiaomi-m11a"
BASE_PHY_COMPATIBLE = b"qcom,csiphy-v2.1.3"
PLATFORM_COMPATIBLES = {
    b"qcom,cci": 2,
    b"qcom,csiphy": 6,
    b"qcom,cam-cpas": 1,
    b"qcom,cam-req-mgr": 1,
}
FORBIDDEN_COMPATIBLES = frozenset({
    b"qcom,cam-sensor",
    b"qcom,camera-flash",
    b"qcom,cam-i2c-flash",
    b"qcom,actuator",
    b"qcom,eeprom",
    b"qcom,ois",
})
MANDATORY_INCLUDES = (
    "<dt-bindings/clock/qcom,gcc-waipio.h>",
    "<dt-bindings/clock/qcom,camcc-waipio.h>",
    "<dt-bindings/interconnect/qcom,waipio.h>",
    "<dt-bindings/interrupt-controller/arm-gic.h>",
    "<dt-bindings/regulator/qcom,rpmh-regulator-levels.h>",
)


def git(path, *args):
    return subprocess.check_output(
        ["git", "-C", str(path), *args], text=True).strip()


def validate_overlay_source(source):
    # Exact structure, no input from the reference Flame/MTP/QRD sensors.
    if source.count(EXPECTED_IMPORT) != 1 or "/plugin/;" not in source:
        raise ValueError("missing dedicated manufacturer Cape platform include")
    if source.count("#include ") != 6:
        raise ValueError("unexpected Camera header or donor include")
    for header in MANDATORY_INCLUDES:
        if source.count("#include " + header) != 1:
            raise ValueError("missing required pinned Qualcomm header " + header)
    # Only two board-specific PHY compatible overrides are permitted.
    # Reject any extra nodes/properties, including GPIO, flash and sensors.
    without_comments = re.sub(r"/\*.*?\*/", "", source,
                              flags=re.DOTALL)
    without_comments = re.sub(r"//.*", "", without_comments)
    for phy in MONDRIAN_M11A_PHY_IDS:
        pattern = re.compile(
            r"&cam_csiphy" + str(phy) +
            r'\s*\{\s*compatible\s*=\s*' +
            r'"qcom,csiphy-v2[.]1[.]3-xiaomi-m11a"\s*,\s*' +
            r'"qcom,csiphy"\s*;\s*\}'
        )
        if len(pattern.findall(without_comments)) != 1:
            raise ValueError("missing or duplicate M11A CSIPHY" + str(phy))
        without_comments = pattern.sub("", without_comments, count=1)
    if re.search(r"\b(?:model|compatible|qcom,board-id|xiaomi,miboard-id)\s*=",
                 without_comments):
        raise ValueError("Camera overlay contains an unqualified property")
    if any(x in without_comments for x in (
            "camera-sensor-mtp", "camera-sensor-qrd", "camera-sensor-cdp",
            "qcom,camera-flash", "qcom,cam-sensor",
            "gpio356", "GPIO_EN", "pm8350c_switch", "flash-source",
            "sensor-vreg", "sensor-position")):
        raise ValueError("reference sensor/flash/hardware settings forbidden")
    if "{" in without_comments or "}" in without_comments:
        raise ValueError("platform wrapper must contain only manufacturer includes")


def compatible(props):
    data = props.get("compatible", b"")
    if len(data) > 4096 or (data and not data.endswith(b"\0")):
        raise ValueError("invalid FDT compatible string array")
    return set(data.rstrip(b"\0").split(b"\0")) if data else set()


def assert_baseline_preserved(before, after):
    """Camera overlay may add nodes but cannot overwrite prior OEM properties."""
    for path, original in before.items():
        if path not in after:
            raise ValueError("Camera overlay removed OEM node: " + path)
        for prop, value in original.items():
            if after[path].get(prop) != value:
                raise ValueError(
                    "Camera overlay rewrote existing OEM property: " +
                    path + ":" + prop)
    return True


def verify_camera_platform_nodes(before, after):
    assert_baseline_preserved(before, after)
    found = {}
    for key, expected_count in PLATFORM_COMPATIBLES.items():
        matched = sorted(
            path for path, props in after.items()
            if key in compatible(props))
        old = [
            path for path, props in before.items()
            if key in compatible(props)
        ]
        if old or len(matched) != expected_count:
            raise ValueError(
                "unexpected original/new Camera platform controller count: " +
                key.decode("ascii"))
        found[key.decode("ascii")] = matched
    indices = {}
    for path in found["qcom,csiphy"]:
        props = after[path]
        cell = props.get("cell-index", b"")
        if len(cell) != 4:
            raise ValueError("invalid Camera PHY cell-index: " + path)
        phy = int.from_bytes(cell, byteorder="big")
        if phy not in range(6) or phy in indices:
            raise ValueError("invalid or duplicate Camera PHY index: " + path)
        indices[phy] = path
        version = (M11A_COMPATIBLE if phy in MONDRIAN_M11A_PHY_IDS
                   else BASE_PHY_COMPATIBLE)
        if props.get("compatible") != version + b"\0qcom,csiphy\0":
            raise ValueError("incorrect mondrian CSI PHY compatible: " + path)
    if set(indices) != set(range(6)):
        raise ValueError("incomplete six-PHY mondrian controller layout")
    for path, props in after.items():
        if compatible(props) & FORBIDDEN_COMPATIBLES:
            raise ValueError("unqualified Camera sensor or flash consumer: " + path)
    return found


def canonical_nodes(image, temp, label):
    inspected = temp / (label + "-inspection.dtb")
    evidence = canonicalize_generated_overlay_fdt(image, inspected)
    return fdt_nodes(inspected.read_bytes()), evidence


def verify_board_routes(before, after, hal_manifest):
    symbols = {name: raw.rstrip(b"\0").decode()
               for name, raw in after["/__symbols__"].items()}

    def cells(*values):
        return struct.pack(">" + "I" * len(values), *values)

    def expect(path, key, value):
        if after[path].get(key) != value:
            raise ValueError(f"incorrect mondrian camera route {path} {key}")

    def handle(label):
        return after[symbols[label]]["phandle"]

    mask = (symbols["pm8350c_switch0"], "qcom,led-mask")
    changes = {mask: cells(1)}
    for bus, strength in enumerate((4, 8, 4, 4)):
        states = ("active",) if bus == 3 else ("active", "suspend")
        for state in states:
            pin = symbols[f"cci{bus}_{state}"] + "/config"
            changes[pin, "drive-strength"] = cells(strength)
    for (path, prop), value in changes.items():
        expect(path, prop, value)
    for path, props in before.items():
        for prop, value in props.items():
            if (path, prop) not in changes:
                expect(path, prop, value)

    # Stock CCI parent and cci-device are independent on this Qualcomm driver.
    routes = (
        ("wide", 0, 1, None, 2, 1), ("front", 0, 0, 1, 4, None),
        ("ultra", 0, 0, 1, 1, 2), ("macro", 1, 0, None, 0, 3),
    )
    profiles = {item["camera_id"]: item for item in hal_manifest["slots"]}
    if (hal_manifest["device"] != "mondrian" or len(hal_manifest["slots"]) != len(routes)
            or set(profiles) != set(range(len(routes)))):
        raise ValueError("factory camera IDs do not match the four mondrian slots")
    linked_slots = {}
    for slot, (role, parent, master, cci_dev, phy, flash_index) in enumerate(routes):
        profile = profiles[slot]
        if profile["role"] != role or not profile["profiles"]:
            raise ValueError(f"missing {role} factory profile for camera ID {slot}")
        sensor = symbols[f"cam_cci{parent}"] + f"/qcom,cam-sensor{slot}"
        eeprom = f"mondrian_eeprom_{role}"
        for node in (sensor, symbols[eeprom]):
            expect(node, "cell-index", cells(slot))
            expect(node, "cci-master", cells(master))
            expect(node, "cci-device", None if cci_dev is None else cells(cci_dev))
        expect(sensor, "csiphy-sd-index", cells(phy))
        expect(sensor, "eeprom-src", handle(eeprom))
        expect(sensor, "actuator-src", handle("mondrian_wide_actuator") if slot == 0 else None)
        if role == "wide" and not profile["ois_control"]["standalone_subdevice_in_stock_dt"]:
            expect(sensor, "ois-src", None)
        if role == "ultra":
            pins = handle("tlmm") + cells(101, 0) + handle("tlmm") + cells(24, 0)
            expect(sensor, "gpios", pins)
            expect(symbols[eeprom], "gpios", pins)
            expect(sensor, "gpio-reset", cells(1))
            expect(symbols[eeprom], "gpio-reset", None)
        linked_slots[role] = {
            "factory_camera_id": slot,
            "sensor_node": sensor,
            "eeprom_node": symbols[eeprom],
            "ois_src_present": "ois-src" in after[sensor],
        }
        if flash_index is None:
            expect(sensor, "led-flash-src", None)
            continue
        flash = f"mondrian_flash_{role}"
        expect(sensor, "led-flash-src", handle(flash))
        expect(symbols[flash], "cell-index", cells(flash_index))
        for prop, pmic in (("switch", "switch"), ("flash", "flash"), ("torch", "torch")):
            expect(symbols[flash], prop + "-source", handle(f"pm8350c_{pmic}0"))

    shared = symbols["soc"] + "/qcom,cam-res-mgr"
    expect(shared, "qcom,shared-pinctrl-gpios",
           b"".join(handle("tlmm") + cells(pin, 0) for pin in (126, 70, 2, 102)))
    return linked_slots


def validate_pinned_sources(kernel, camera_platform, camera_kernel, board_build):
    verify_kernel_revision(kernel, KERNEL_SHA)
    if git(camera_platform, "rev-parse", "HEAD") != CAMERA_PLATFORM_SHA:
        raise ValueError("unapproved Xiaomi Cape Camera source")
    if git(camera_platform, "rev-parse", "HEAD^{tree}") != CAMERA_PLATFORM_TREE:
        raise ValueError("manufacturer Camera platform tree changed")
    if git(camera_kernel, "rev-parse", "HEAD") != CAMERA_KERNEL_SHA:
        raise ValueError("Camera DTS binding from a different driver revision")
    header = camera_kernel / "dt-bindings/msm-camera.h"
    if git(camera_kernel, "hash-object", "dt-bindings/msm-camera.h") != CAMERA_HEADER_SHA:
        raise ValueError("original Camera kernel dt-binding header drift")
    if not header.is_file():
        raise ValueError("missing original Xiaomi MSM Camera header")
    with (board_build / "dtbo-diagnostic-evidence.json").open() as stream:
        board = json.load(stream)
    selector = board_build / "images" / (BOARD + ".dtbo")
    if hashlib.sha256(selector.read_bytes()).hexdigest() != board["outputs_sha256"][selector.name]:
        raise ValueError("unrecognized mondrian board selector image")
    for key, expected in (("qcom,board-id", [0x10008, 0]), ("xiaomi,miboard-id", [14, 0])):
        cells = subprocess.check_output(["fdtget", "-t", "x", selector, "/", key], text=True)
        if [int(cell, 16) for cell in cells.split()] != expected:
            raise ValueError("incompatible mondrian board selector " + key)
    if (board.get("device") != "mondrian" or
            board.get("kernel") != KERNEL_SHA or
            board.get("oem_device_tree") !=
            "34e6cc7d832ed9c655b9d79bc3ffe1d625146b7c" or
            board.get("board_overlay_applied_to_all_cape_bases") is not True or
            board.get("camera_pmic_oem_source_links_compiled") is not True or
            board.get("bootloader_hardware_verified") is not False):
        raise ValueError("unqualified OEM mondrian board artifact")
    return board


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path, required=True)
    parser.add_argument("--camera-kernel", type=Path, required=True)
    parser.add_argument("--board-build", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    kernel = args.kernel.resolve()
    camera_kernel = args.camera_kernel.resolve()
    camera_platform = ROOT / "upstream/xiaomi-camera-platform"
    board_build = args.board_build.resolve()
    out = args.out.resolve()
    try:
        for command in ("cpp", "dtc", "fdtoverlay", "fdtget"):
            if not shutil.which(command):
                raise RuntimeError("missing build tool " + command)
        validate_overlay_source(OVERLAY.read_text())
        board = validate_pinned_sources(
            kernel, camera_platform, camera_kernel, board_build)
        if out.exists() and any(out.iterdir()):
            raise RuntimeError("Camera diagnostic output directory must be empty")
        out.mkdir(parents=True, exist_ok=True)
        image_dir = out / "images"
        image_dir.mkdir()
        preprocessed = out / "mondrian-camera-platform.preprocessed.dts"
        cmd = ["cpp", "-nostdinc", "-undef", "-D__DTS__",
               "-x", "assembler-with-cpp"]
        for path in (
            kernel / "include",
            kernel / "arch/arm64/boot/dts",
            camera_kernel,             # dt-bindings/msm-camera.h, exact OEM driver
            camera_platform,           # cape-camera.dtsi, exact OEM manufacturer
        ):
            cmd += ["-I", str(path)]
        cmd.append(str(OVERLAY))
        with preprocessed.open("wb") as stream:
            run(cmd, stdout=stream)
        dtbo = image_dir / "mondrian-camera-platform-diagnostic.dtbo"
        run(["dtc", "-@", "-I", "dts", "-O", "dtb", "-o", dtbo,
             preprocessed])
        if dtbo.stat().st_size < 100:
            raise RuntimeError("Camera platform DTBO is invalid or truncated")
        board_cpp = out / "mondrian-camera-board.preprocessed.dts"
        with board_cpp.open("wb") as stream:
            run(["cpp", "-nostdinc", "-undef", "-D__DTS__", "-x",
                 "assembler-with-cpp", "-I", kernel / "include", BOARD_CAMERA],
                stdout=stream)
        board_dtbo = image_dir / "mondrian-camera-board-diagnostic.dtbo"
        run(["dtc", "-@", "-I", "dts", "-O", "dtb", "-o", board_dtbo, board_cpp])
        hal_manifest = json.loads(HAL_PROFILES.read_text())
        result = {}
        for cape in BASES:
            original = board_build / "images" / (
                cape + "-mondrian-merged.dtb")
            if not original.is_file():
                raise RuntimeError("missing coherent OEM " + cape +
                                   " mondrian base board")
            basehash = hashlib.sha256(original.read_bytes()).hexdigest()
            if board["outputs_sha256"].get(original.name) != basehash:
                raise RuntimeError("original board DTB differs from OEM manifest")
            merged = image_dir / (
                cape + "-mondrian-camera-platform-diagnostic.dtb")
            run(["fdtoverlay", "-i", original, "-o", merged, dtbo])
            with TemporaryDirectory(prefix="pe-camera-fdt-", dir=out) as temporary:
                temp = Path(temporary)
                before, binfo = canonical_nodes(original, temp, "before")
                after, ainfo = canonical_nodes(merged, temp, "after")
                controllers = verify_camera_platform_nodes(before, after)
                board_camera = image_dir / (cape + "-mondrian-camera-board-diagnostic.dtb")
                run(["fdtoverlay", "-i", merged, "-o", board_camera, board_dtbo])
                routed, _ = canonical_nodes(board_camera, temp, "board-camera")
                linked_slots = verify_board_routes(after, routed, hal_manifest)
            result[cape] = {
                "original_board_dtb_sha256": basehash,
                "camera_overlay_merged_sha256":
                    hashlib.sha256(merged.read_bytes()).hexdigest(),
                "controller_paths": controllers,
                "camera_slots": linked_slots,
                "camera_board_merged_sha256": hashlib.sha256(board_camera.read_bytes()).hexdigest(),
                "manufacturer_board_properties_preserved": True,
                "camera_base_and_overlay_dts_reencoded_for_inspection": True,
                "base_inspection_dts_unchanged": binfo[
                    "complete_original_and_canonical_dts_identical"],
                "merged_inspection_dts_unchanged": ainfo[
                    "complete_original_and_canonical_dts_identical"],
            }
        evidence = {
            "status": "DIAGNOSTIC_CAPE_CAMERA_PLATFORM_COMPILED_NOT_SHIP_READY",
            "device": "mondrian",
            "android_base": "AOSP 17",
            "kernel_commit": KERNEL_SHA,
            "manufacturer_camera_dts_commit": CAMERA_PLATFORM_SHA,
            "manufacturer_camera_kernel_commit": CAMERA_KERNEL_SHA,
            "camera_platform_dtbo_sha256":
                hashlib.sha256(dtbo.read_bytes()).hexdigest(),
            "camera_board_dtbo_sha256": hashlib.sha256(board_dtbo.read_bytes()).hexdigest(),
            "board_sensor_eeprom_routes_linked": True,
            "factory_camera_hal_profiles": hal_manifest,
            "board_rear_flash_switch0_mask": 1,
            "all_three_cape_base_dtb_links_resolved": True,
            "per_board": result,
            "mondrian_m11a_csiphy2_and_4_bound": True,
            "sensor_power_configured": True,
            "sensor_power_sequence_hardware_verified": False,
            "mondrian_camera_sensor_addresses_verified": False,
            "pm8350c_flash_channels_verified": False,
            "camera_hal_integration_tested": False,
            "physical_camera_hardware_tested": False,
            "production_camera_dtbo_approved": False,
        }
        (out / "mondrian-camera-platform-diagnostic-evidence.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n")
        print("[PASS] pinned OEM Cape Camera CCI/CSI/CPAS applied to all mondrian Cape bases")
        print("[PASS] four mondrian sensor/EEPROM routes and three rear flash consumers linked")
        print("[PENDING] sensor probing, power sequencing, PM8350C and Camera HAL on hardware")
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as e:
        print("[FAIL] Camera platform diagnostic: " + str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

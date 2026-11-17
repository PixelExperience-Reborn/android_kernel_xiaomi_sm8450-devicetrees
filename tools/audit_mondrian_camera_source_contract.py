#!/usr/bin/env python3
"""Source-only Camera compatibility gate for PE-Reborn mondrian (SM8475).

This checks original OEM board facts against the separately pinned
manufacturer Cape controllers. It deliberately does not select any
camera sensor, flash channel, power sequence, HAL or production DTBO.
No stock firmware, proprietary blob, or foreign ROM input is used.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_BLOBS = {
    "qcom/mondrian-sm8475-pm8008-overlay.dts":
        "46e60415b9287309e5290a6d32654f14d2b2ab42",
    "qcom/mondrian-wl2866d.dtsi":
        "539502c463a993042c8a6af25fd24e99110496c8",
    "upstream/xiaomi-camera-platform/cape-camera.dtsi":
        "700405437360cc2cd6465ca0f886bd64781f92a9",
}
REQUIRED_CCI_NODES = ("cam_cci0:", "cam_cci1:")
REQUIRED_PHY_NODES = tuple(f"cam_csiphy{i}:" for i in range(6))


def git_blob_sha(content):
    return hashlib.sha1(
        b"blob " + str(len(content)).encode("ascii") + b"\0" + content
    ).hexdigest()


def original_source(path):
    content = (ROOT / path).read_bytes()
    if git_blob_sha(content) != ORIGINAL_BLOBS[path]:
        raise ValueError("pinned OEM Camera source changed: " + path)
    return content.decode("utf-8")


def validate_board(regulator, board):
    """Only report hardware facts explicitly in original mondrian source."""
    required = {
        "own board include": '#include "mondrian-wl2866d.dtsi"' in board,
        "own board dtsi": '#include "mondrian-sm8475.dtsi"' in board,
        "WL2866D compatible": 'compatible = "xiaomi,wl2866d";' in regulator,
        "WL2866D bus": bool(re.search(r"&qupv3_se5_i2c\s*\{", regulator)),
        "WL2866D unit address": bool(re.search(r"\bwl2866d@28\s*\{", regulator)),
        "WL2866D i2c address": bool(re.search(r"\breg\s*=\s*<0x28>\s*;", regulator)),
        "WL2866D vin1": bool(re.search(r"vin1-supply\s*=\s*<&S12B>\s*;", regulator)),
        "WL2866D vin2": bool(re.search(r"vin2-supply\s*=\s*<&BOB>\s*;", regulator)),
        "WL2866D enable": bool(re.search(r"en-gpio\s*=\s*<&tlmm\s+44\s+0>\s*;", regulator)),
    }
    missing = [name for name, present in required.items() if not present]
    if missing:
        raise ValueError("incomplete original mondrian source: " + ", ".join(missing))
    return required


def validate_donor_controller_source(cape, overlay):
    """Generic platform may be built, but donor board wiring is prohibited."""
    from build_mondrian_camera_platform import validate_overlay_source
    validate_overlay_source(overlay)
    required = REQUIRED_CCI_NODES + REQUIRED_PHY_NODES + (
        'compatible = "qcom,cam-cpas"',
        'compatible = "qcom,cam-req-mgr"',
    )
    missing = [item for item in required if cape.count(item) != 1]
    if missing:
        raise ValueError("manufacturer controller source drift: " + repr(missing))
    # This wrapper must never select reference-board sensor or flash DTS.
    if re.search(r'#include\s+"(?:cape|flame|ukee)-camera-sensor-', overlay):
        raise ValueError("unqualified donor sensor source was included")
    return {"cci_count": 2, "csiphy_count": 6,
            "cpas_count": 1, "camera_request_manager_count": 1}


def audit():
    board = original_source("qcom/mondrian-sm8475-pm8008-overlay.dts")
    regulator = original_source("qcom/mondrian-wl2866d.dtsi")
    cape = original_source("upstream/xiaomi-camera-platform/cape-camera.dtsi")
    overlay = (ROOT / "qcom/mondrian-sm8475-camera-platform-overlay.dts").read_text()
    validate_board(regulator, board)
    controllers = validate_donor_controller_source(cape, overlay)
    return {
        "status": "OEM_SOURCE_CONTRACT_VERIFIED_SENSOR_BOARD_WIRING_UNQUALIFIED",
        "project": "PixelExperience-Reborn",
        "device": "mondrian",
        "soc": "SM8475",
        "android_base": "AOSP 17",
        "evidence_type": "PINNED_MANUFACTURER_SOURCE_ONLY",
        "oem_board_regulator": {
            "compatible": "xiaomi,wl2866d",
            "i2c_controller_label": "qupv3_se5_i2c",
            "i2c_address": "0x28",
            "vin1_source_label": "S12B",
            "vin2_source_label": "BOB",
            "enable_gpio_controller_label": "tlmm",
            "enable_gpio_number": 44,
            "camera_sensor_rail_associations_verified": False,
        },
        "candidate_donor_controller_source":
            "MiCode/vendor_qcom_proprietary_camera-devicetree@a59a63bd498b94074c41357a466874b99aec62a8",
        "controller_definitions": controllers,
        "device_specific_camera_sensor_nodes_qualified": False,
        "cci_i2c_sensor_routes_qualified": False,
        "csi_lane_mappings_qualified": False,
        "camera_reset_and_power_sequence_qualified": False,
        "eeprom_actuator_ois_mapping_qualified": False,
        "pm8350c_camera_flash_mapping_qualified": False,
        "camera_driver_abi_and_module_symvers_qualified": False,
        "camera_hal_integration_qualified": False,
        "physical_hardware_verified": False,
        "stock_firmware_or_blobs_used": False,
        "external_rom_source_imported": False,
        "production_camera_dtbo_approved": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit()
        args.out.mkdir(parents=True, exist_ok=True)
        dest = args.out / "mondrian-camera-oem-source-contract.json"
        dest.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    except (OSError, ValueError) as exc:
        print("[FAIL] Camera OEM source contract: " + str(exc), file=sys.stderr)
        return 1
    print("[PASS] pinned mondrian WL2866D board source and Cape controllers verified")
    print("[PENDING] sensor wiring, power, CSI routes, driver ABI and hardware")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

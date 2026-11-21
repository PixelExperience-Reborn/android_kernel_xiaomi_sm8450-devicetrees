#!/usr/bin/env python3
"""Source integrity gate: Xiaomi-authored Cape CCI/CSIPHY/CPAS, mondrian only.

The official MiCode 'flame-u-oss' branch contains generic Cape controller
definitions but its sensor-specific overlays are not mondrian data. This gate
pins the upstream manufacturer source unchanged, verifies compatibility
strings from the pinned OEM Camera kernel and forbids activating donor sensors.
"""
import configparser
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = "upstream/xiaomi-camera-platform"
SOURCE_REPOSITORY = "MiCode/vendor_qcom_proprietary_camera-devicetree"
SOURCE_URL = "https://github.com/" + SOURCE_REPOSITORY + ".git"
SOURCE_COMMIT = "a59a63bd498b94074c41357a466874b99aec62a8"
SOURCE_TREE = "dcd9bc5855358af4a3c39a9a582472d3190766cc"
DRIVER_COMMIT = "9ed4ce96d49c0759c6365627113c5f59c2407942"
FILE_BLOBS = {
    "cape-camera.dtsi": "700405437360cc2cd6465ca0f886bd64781f92a9",
    "cape-camera.dts": "c2b0db102075a61f167758dd4c641551fc65c4b2",
    "config/waipio.mk": "b451a595dc51297af9d08787b661942c0903d4bf",
    "bindings/msm-cam-cci.txt": "52853e40f0fa957afd8418a3295837f653ef457c",
}
PLATFORM_CONTROLLERS = (
    "cam_cci0: qcom,cci0@ac15000",
    "cam_cci1: qcom,cci1@ac16000",
    "cam_csiphy0: qcom,csiphy0@ace4000",
    "cam_csiphy1: qcom,csiphy1@ace6000",
    "cam_csiphy2: qcom,csiphy2@ace8000",
    "cam_csiphy3: qcom,csiphy3@acea000",
    "cam_csiphy4: qcom,csiphy4@acec000",
    "cam_csiphy5: qcom,csiphy5@acee000",
    'compatible = "qcom,cam-cpas"',
    'compatible = "qcom,cam-req-mgr"',
)
MANDATORY_FLAGS = {
    "target_device_only": "mondrian",
    "original_xiaomi_kernel_devicetree_unchanged": True,
    "sensor_overlays_from_reference_device_compiled": False,
    "cape_platform_camera_overlay_compiled": False,
    "mondrian_camera_sensor_mapping_verified": False,
    "camera_flash_pmic_channel_mapping_verified": False,
    "camera_hal_mapped": False,
    "booted_on_mondrian": False,
    "fm_radio_included": False,
    "lineage_source_imported": False,
    "production_camera_dtbo_approved": False,
}


def git(root, *args):
    return subprocess.check_output(
        ["git", "-C", str(root), *args], text=True).strip()


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() +
                        b"\0" + data).hexdigest()


def verify_config(data):
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(data)
    entries = {
        'submodule "upstream/xiaomi-dts"': {
            "path": "upstream/xiaomi-dts",
            "url": "https://github.com/MiCode/kernel_devicetree.git",
        },
        'submodule "' + SOURCE_PATH + '"': {
            "path": SOURCE_PATH,
            "url": SOURCE_URL,
        },
        'submodule "upstream/xiaomi-display"': {
            "path": "upstream/xiaomi-display",
            "url": "https://github.com/MiCode/vendor_qcom_proprietary_display-devicetree.git",
        },
    }
    if set(parser.sections()) != set(entries):
        raise ValueError("unexpected OEM submodules or missing manufacturer source")
    for section, expected in entries.items():
        if dict(parser[section]) != expected:
            raise ValueError("wrong OEM submodule path/URL: " + section)


def verify_lock(data):
    expected = {
        "schema_version": 1,
        "project": "PixelExperience-Reborn",
        "device": "mondrian",
        "soc": "SM8475",
        "android_base": "AOSP 17",
        "driver": {
            "repository": "MiCode/vendor_qcom_opensource_camera-kernel",
            "commit": DRIVER_COMMIT,
        },
        "manufacturer_platform": {
            "repository": SOURCE_REPOSITORY,
            "commit": SOURCE_COMMIT,
            "tree": SOURCE_TREE,
            "revision_branch": "flame-u-oss",
            "selection": "generic Cape controller definitions only; no flame sensor configuration",
            "files": FILE_BLOBS,
        },
        "policy": MANDATORY_FLAGS,
        "status": "MANUFACTURER_CAPE_CAMERA_PLATFORM_SOURCE_PINNED_NOT_COMPILED",
    }
    if data != expected:
        raise ValueError("unreviewed Camera platform source, ABI or board qualification")


def verify_gitlink(value):
    if value != "160000 commit " + SOURCE_COMMIT + "\t" + SOURCE_PATH:
        raise ValueError("Xiaomi Camera Gitlink path/SHA changed")


def verify_cape_platform_source(content, cape_dts):
    # These are only manufacturer-generic controller declarations.
    for signal in PLATFORM_CONTROLLERS:
        if content.count(signal) != 1:
            raise ValueError("missing/ambiguous original Cape controller: " + signal)
    if content.count('compatible = "qcom,cci", "simple-bus";') != 2:
        raise ValueError("unexpected number of Qualcomm CCI compatibles")
    if not cape_dts.count('#include "cape-camera.dtsi"') == 1:
        raise ValueError("Cape board target is not backed by manufacturer DTS")
    if '#include "cape-camera-sensor-' in cape_dts:
        raise ValueError("manufacturer reference sensor definitions mixed into platform")
    if not all(x in cape_dts for x in (
        'compatible = "qcom,cape", "qcom,capep";',
        'qcom,board-id = <0 0>;',
    )):
        raise ValueError("generic Cape test target modified unexpectedly")
    # GPIO definitions in this upstream source are never enabled by this
    # gate: their applicability to a physical mondrian SKU is unverified.


def verify_checkout(root):
    verify_config((root / ".gitmodules").read_text())
    verify_lock(json.loads(
        (root / "mondrian-camera-platform-source-lock.json").read_text()))
    verify_gitlink(git(root, "ls-tree", "HEAD", SOURCE_PATH))
    camera = root / SOURCE_PATH
    if git(camera, "rev-parse", "HEAD") != SOURCE_COMMIT:
        raise ValueError("Camera source revision differs from locked MiCode Gitlink")
    if git(camera, "rev-parse", "HEAD^{tree}") != SOURCE_TREE:
        raise ValueError("Camera source Git tree differs from manufacturer")
    if git(camera, "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("manufacturer source checkout contains tracked edits")
    for path, expected in FILE_BLOBS.items():
        if git_blob((camera / path).read_bytes()) != expected:
            raise ValueError("modified manufacturer platform blob: " + path)
    verify_cape_platform_source(
        (camera / "cape-camera.dtsi").read_text(),
        (camera / "cape-camera.dts").read_text())
    # The existing independently checked OEM mondrian board must *not*
    # include the generic reference board or donor-specific sensor overlays.
    own = (root / "qcom/mondrian-sm8475-pm8008-overlay.dts").read_text()
    for forbidden in ("cape-camera.dtsi", "cape-camera.dts",
                      "cape-camera-sensor-", "flame-camera-sensor-",
                      "ukee-camera-sensor-"):
        if forbidden in own:
            raise ValueError("unqualified donor Camera included in mondrian overlay")
    return True


def main():
    try:
        verify_checkout(ROOT)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print("[FAIL] OEM Cape Camera source: " + str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    print("[PASS] MiCode Cape CCI0/CCI1, CSIPHY0..5 and CPAS sources pinned")
    print("[PASS] Existing mondrian DTB untouched; no donor sensor tree enabled")
    print("[PENDING] Adapt native mondrian Camera board DTS, compile & test")


if __name__ == "__main__":
    main()

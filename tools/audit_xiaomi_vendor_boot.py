#!/usr/bin/env python3
"""Read-only AOSP v3/v4 vendor_boot DTB inspection for Xiaomi mondrian.

Uses the Android 17 vendor_boot_img_hdr_v3/v4 layout from AOSP
platform/system/tools/mkbootimg/include/bootimg/bootimg.h.
Only DTB checksums and feature-presence indicators enter the JSON result.
This does not establish Xiaomi firmware authenticity or panel readiness.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess

from audit_xiaomi_stock_dtbo import FDT_MAGIC, inspect_dts, parse_fdt

MAGIC = b"VNDRBOOT"
V3_HEADER_SIZE = 2112
V4_HEADER_SIZE = 2128
MAX_DTB_BYTES = 128 * 1024 * 1024
MAX_VENDOR_BOOT_BYTES = 512 * 1024 * 1024
MAX_DTBS = 256


def _le32(source, offset):
    return struct.unpack_from("<I", source, offset)[0]


def _be32(source, offset):
    return struct.unpack_from(">I", source, offset)[0]


def _align(value, page):
    return (value + page - 1) // page * page


def parse_vendor_boot(image):
    """Return validated metadata and exact embedded FDT byte sequences.

    This parser does not read ramdisk data, silently search for arbitrary FDT
    magic, decompress partitions, or claim a bootable image. Non-FDT trailing
    bytes in the advertised DTB section are an error; zero alignment is fine.
    """
    if len(image) < V3_HEADER_SIZE or not image.startswith(MAGIC):
        raise ValueError("invalid AOSP vendor_boot header or magic")
    version = _le32(image, 8)
    if version not in (3, 4):
        raise ValueError("only AOSP vendor_boot header versions 3/4 are supported")
    header_size = _le32(image, 2096)
    expected = V3_HEADER_SIZE if version == 3 else V4_HEADER_SIZE
    if len(image) < expected or header_size != expected:
        raise ValueError("unexpected AOSP vendor_boot header size")
    page = _le32(image, 12)
    if page not in (2048, 4096, 8192, 16384, 32768, 65536):
        raise ValueError("invalid vendor_boot page size")
    vendor_ramdisk_size = _le32(image, 24)
    dtb_size = _le32(image, 2100)
    if dtb_size > MAX_DTB_BYTES or len(image) > MAX_VENDOR_BOOT_BYTES:
        raise ValueError("vendor_boot image or DTB section exceeds audit limits")
    dtb_offset = _align(header_size, page) + _align(vendor_ramdisk_size, page)
    if dtb_offset > len(image) or dtb_offset + dtb_size > len(image):
        raise ValueError("vendor_boot DTB region outside image bounds")
    # v4 follows DTBs with the vendor ramdisk table, then bootconfig.
    if version == 4:
        table_size = _le32(image, 2112)
        entry_count = _le32(image, 2116)
        entry_size = _le32(image, 2120)
        bootconfig_size = _le32(image, 2124)
        if entry_count and (not entry_size or entry_count * entry_size > table_size):
            raise ValueError("invalid v4 vendor ramdisk table metadata")
        remaining_offset = dtb_offset + _align(dtb_size, page)
        if (remaining_offset + _align(table_size, page) + bootconfig_size
                > len(image)):
            raise ValueError("v4 vendor ramdisk table / bootconfig exceeds image")
    dtbs = []
    blob = memoryview(image)[dtb_offset:dtb_offset + dtb_size]
    position = 0
    while position < len(blob):
        # Only zero bytes can appear between independently concatenated DTBs.
        while position < len(blob) and blob[position] == 0:
            position += 1
        if position >= len(blob):
            break
        if len(blob) - position < 40 or _be32(blob, position) != FDT_MAGIC:
            raise ValueError(f"invalid FDT in vendor_boot DTB region at {position}")
        if len(dtbs) >= MAX_DTBS:
            raise ValueError("vendor_boot contains too many DTBs")
        fdt = parse_fdt(blob[position:].tobytes())
        dtbs.append(fdt)
        position += len(fdt)
    return {
        "header_version": version,
        "page_size": page,
        "vendor_ramdisk_size": vendor_ramdisk_size,
        "dtb_size": dtb_size,
        "dtb_section_offset": dtb_offset,
    }, dtbs


def audit_vendor_boot_data(data):
    """Summarize only original DTB SHA256 and candidate panel indicators."""
    header, dtbs = parse_vendor_boot(data)
    if dtbs and not shutil.which("dtc"):
        raise RuntimeError("dtc is required for vendor_boot DTB inspection")
    entries = []
    for index, blob in enumerate(dtbs):
        proc = subprocess.run(
            ["dtc", "-q", "-I", "dtb", "-O", "dts"],
            input=blob, capture_output=True, check=True)
        decoded = proc.stdout.decode("utf-8", errors="replace")
        entries.append({
            "index": index,
            "dtb_sha256": hashlib.sha256(blob).hexdigest(),
            "candidate_signals": inspect_dts(decoded),
        })
    return {
        "present": True,
        "image_sha256": hashlib.sha256(data).hexdigest(),
        "header": header,
        "embedded_dtb_count": len(entries),
        "embedded_dtbs": entries,
        "manufacturer_provenance_independently_verified": False,
        "m11a_panel_ready": False,
        "status": "DIAGNOSTIC_ONLY_NOT_FOR_FLASHING",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendor-boot", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        data = args.vendor_boot.read_bytes()
        result = audit_vendor_boot_data(data)
        args.out.mkdir(parents=True, exist_ok=True)
        output = args.out / "xiaomi-stock-vendor-boot-diagnostic.json"
        output.write_text(json.dumps(result, indent=2) + "\n")
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        parser.error(str(exc))
    print(f"[PASS] Parsed stock vendor_boot DTB section: {output}")
    print("[BLOCKED] Panel M11A / LHBM / product DTBO not certified")


if __name__ == "__main__":
    main()

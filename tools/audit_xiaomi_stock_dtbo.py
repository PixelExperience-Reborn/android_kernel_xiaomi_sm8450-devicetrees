#!/usr/bin/env python3
"""Read-only Xiaomi stock DTBO provenance/contents audit for mondrian.

Does NOT generate a product DTS or qualify an M11A panel for use. The image
must be provided from the actual Xiaomi stock firmware for the device.
Never substitute a third-party ROM DTBO for manufacturer evidence.
"""
import argparse
import hashlib
import json
import shutil
import struct
import subprocess
from pathlib import Path

DT_TABLE_MAGIC = 0xD7B7AB1E
FDT_MAGIC = 0xD00DFEED
MAX_ENTRIES = 256


def _u32(data, offset):
    return struct.unpack_from(">I", data, offset)[0]


def parse_fdt(data):
    """Validate the fixed FDT header and return its advertised exact bytes."""
    if len(data) < 40 or _u32(data, 0) != FDT_MAGIC:
        raise ValueError("not a valid FDT header")
    length = _u32(data, 4)
    if length < 40 or length > len(data):
        raise ValueError("FDT totalsize outside image bounds")
    # FDT sections must stay inside the advertised DTB, not just padding.
    off_struct, off_strings, off_reserve = struct.unpack_from(">3I", data, 8)
    size_strings, size_struct = struct.unpack_from(">2I", data, 32)
    if any(off > length for off in (off_struct, off_strings, off_reserve)):
        raise ValueError("FDT section offset outside totalsize")
    if off_struct + size_struct > length or off_strings + size_strings > length:
        raise ValueError("FDT section overflows totalsize")
    return data[:length]


def parse_android_dtbo(data):
    """Return (entry index, hardware id, revision, exact FDT bytes)."""
    if len(data) < 32:
        raise ValueError("DTBO image shorter than header")
    if _u32(data, 0) == FDT_MAGIC:
        return [(0, None, None, parse_fdt(data))]
    magic, total, header, item_size, count, offset, _page, version = (
        struct.unpack_from(">8I", data))
    if magic != DT_TABLE_MAGIC:
        raise ValueError("missing Android DT table magic / raw DTB header")
    if total < 32 or total > len(data):
        raise ValueError("Android DT table size outside file bounds")
    if header < 32 or header > total or item_size < 32:
        raise ValueError("invalid DT table header/entry size")
    if count == 0 or count > MAX_ENTRIES:
        raise ValueError("invalid DT entry count")
    if offset < header or offset + count * item_size > total:
        raise ValueError("DT entries extend outside table")
    # Android's published DT table v0 layout is the only format validated here.
    if version != 0:
        raise ValueError("unsupported Android DT table version")
    entries = []
    for i in range(count):
        size, location, board_id, revision = struct.unpack_from(
            ">4I", data, offset + i * item_size)
        if size < 40 or location < header or location + size > total:
            raise ValueError(f"DT entry {i} outside declared image bounds")
        if location < offset + count * item_size and location + size > offset:
            raise ValueError(f"DT entry {i} overlaps table metadata")
        payload = data[location:location + size]
        fdt = parse_fdt(payload)
        # OEM image packers may add alignment padding. Accept it only if it
        # consists of zero bytes, never silently hide non-FDT payload.
        if any(payload[len(fdt):]):
            raise ValueError(f"DT entry {i} contains nonzero trailing data")
        entries.append((i, board_id, revision, fdt))
    return entries


def inspect_dts(dts):
    """Only report candidates; a matching string never certifies hardware."""
    dts = dts.lower()
    return {
        "mentions_m11a": "m11a" in dts,
        "panel_description_present": (
            "qcom,mdss-dsi-panel-name" in dts
            and "qcom,mdss-dsi-panel-width" in dts
            and "qcom,mdss-dsi-panel-height" in dts
        ),
        "dsc_property_present": "qcom,mdss-dsc-slice-width" in dts,
        "xiaomi_local_hbm_property_present": "mi,local-hbm-enabled" in dts,
        "xiaomi_board_id_property_present": "xiaomi,miboard-id" in dts,
    }


def audit(dtbo_path, *, package_sha256, output):
    data = dtbo_path.read_bytes()
    if not data:
        raise ValueError("input stock image is empty")
    entries = parse_android_dtbo(data)
    if not shutil.which("dtc"):
        raise RuntimeError("dtc is required to inspect FDT properties")
    output.mkdir(parents=True, exist_ok=True)
    results = []
    for index, board_id, revision, fdt in entries:
        proc = subprocess.run(["dtc", "-q", "-I", "dtb", "-O", "dts"],
                              input=fdt, capture_output=True, check=True)
        decoded = proc.stdout.decode("utf-8", errors="replace")
        record = {
            "entry_index": index,
            "entry_id": board_id,
            "entry_revision": revision,
            "dtb_sha256": hashlib.sha256(fdt).hexdigest(),
            "candidate_signals": inspect_dts(decoded),
        }
        results.append(record)
    evidence = {
        "device": "mondrian",
        "declared_manufacturer": "Xiaomi",
        "package_sha256_user_supplied": package_sha256,
        "dtbo_image_sha256": hashlib.sha256(data).hexdigest(),
        "image_length": len(data),
        "entries": results,
        "source_authenticity_independently_verified": False,
        "m11a_panel_ready": False,
        "production_dtbo_approved": False,
        "status": "DIAGNOSTIC_ONLY_NOT_FOR_FLASHING",
    }
    path = output / "xiaomi-stock-dtbo-diagnostic.json"
    path.write_text(json.dumps(evidence, indent=2) + "\n")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dtbo", required=True, type=Path,
                        help="dtbo.img extracted from official Xiaomi stock firmware")
    parser.add_argument("--package-sha256", required=True,
                        help="SHA256 of Xiaomi source fastboot/OTA archive")
    parser.add_argument("--out", required=True, type=Path,
                        help="local directory for JSON-only diagnostic evidence")
    args = parser.parse_args()
    if len(args.package_sha256) != 64 or any(
            c not in "0123456789abcdefABCDEF" for c in args.package_sha256):
        parser.error("stock package SHA256 must contain exactly 64 hex digits")
    try:
        path = audit(args.dtbo, package_sha256=args.package_sha256.lower(),
                     output=args.out)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        parser.error(str(exc))
    print(f"[PASS] Parsed Xiaomi-supplied DTBO data: {path}")
    print("[BLOCKED] DTS provenance, M11A panel, LHBM and production readiness NOT verified")


if __name__ == "__main__":
    main()

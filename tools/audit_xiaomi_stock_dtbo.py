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

# Imported lazily below: panel parser also imports the minimal FDT header
# validator from this module, avoiding an import cycle.
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


MAX_DECOMPRESSED_DTB_BYTES = 64 * 1024 * 1024
COMPRESSION_NAMES = ("none", "zlib", "gzip", "lz4")


def _inflate_entry(payload, compression, index):
    """Decode official AOSP mkdtboimg compression with an explicit output cap.

    The original compressed bytes remain in the stock image, are never written
    to the PE device tree and are not independently proof of manufacturer origin.
    """
    if compression == 0:
        return payload
    if compression in (1, 2):
        decoder = zlib.decompressobj(15 if compression == 1 else 31)
        try:
            output = decoder.decompress(payload, MAX_DECOMPRESSED_DTB_BYTES + 1)
            if len(output) > MAX_DECOMPRESSED_DTB_BYTES or decoder.unconsumed_tail:
                raise ValueError(f"DT entry {index} exceeds decompressed size limit")
            output += decoder.flush(MAX_DECOMPRESSED_DTB_BYTES + 1 - len(output))
        except zlib.error as exc:
            raise ValueError(f"DT entry {index} has corrupt compressed data") from exc
        if (len(output) > MAX_DECOMPRESSED_DTB_BYTES or not decoder.eof or
                decoder.unused_data):
            raise ValueError(f"DT entry {index} has truncated/trailing compressed data")
        return output
    if compression == 3:
        try:
            import lz4.frame
        except ImportError as exc:
            raise ValueError(
                "LZ4 compressed stock DTBO requires optional Python lz4.frame") from exc
        try:
            decoder = lz4.frame.LZ4FrameDecompressor()
            output = decoder.decompress(
                payload, max_length=MAX_DECOMPRESSED_DTB_BYTES + 1)
        except (RuntimeError, ValueError) as exc:
            raise ValueError(f"DT entry {index} has corrupt LZ4 compressed data") from exc
        if (len(output) > MAX_DECOMPRESSED_DTB_BYTES or not decoder.eof or
                decoder.unused_data):
            raise ValueError(f"DT entry {index} has oversized/trailing LZ4 data")
        return output
    raise ValueError(f"unsupported DT entry {index} compression format {compression}")


def parse_android_dtbo(data, *, with_metadata=False):
    """Parse official AOSP DT table versions 0, 1 and 2 or a raw FDT.

    Legacy call sites receive the original (index, id, rev, FDT) tuples.
    with_metadata=True also returns version/flags/custom fields needed for
    manufacturer SKU review without assigning a guessed board selection.
    """
    if len(data) < 32:
        raise ValueError("DTBO image shorter than header")
    if _u32(data, 0) == FDT_MAGIC:
        fdt = parse_fdt(data)
        item = {
            "index": 0, "id": None, "revision": None,
            "table_version": None, "entry_flags": 0,
            "compression": "none", "custom_fields": [],
            "table_page_size": None, "fdt": fdt,
        }
        return [item] if with_metadata else [(0, None, None, fdt)]
    magic, total, header, item_size, count, offset, page_size, version = (
        struct.unpack_from(">8I", data))
    if magic != DT_TABLE_MAGIC:
        raise ValueError("missing Android DT table magic / raw DTB header")
    if total < 32 or total > len(data):
        raise ValueError("Android DT table size outside file bounds")
    if header != 32:
        raise ValueError("invalid Android DT table header size")
    expected = {0: 32, 1: 32, 2: 64}.get(version)
    if expected is None:
        raise ValueError(f"unsupported Android DT table version {version}")
    if item_size != expected:
        raise ValueError("invalid Android DT entry size for table version")
    if not (page_size and (page_size & (page_size - 1)) == 0 and
            512 <= page_size <= 65536):
        raise ValueError("invalid Android DT table page size")
    if count == 0 or count > MAX_ENTRIES:
        raise ValueError("invalid DT entry count")
    metadata_end = offset + count * item_size
    if offset < header or metadata_end > total:
        raise ValueError("DT entries extend outside table")
    entries = []
    for index in range(count):
        words = struct.unpack_from(
            ">" + ("8I" if version in (0, 1) else "16I"),
            data, offset + index * item_size)
        size, location, board_id, revision = words[:4]
        flags = 0 if version == 0 else words[4]
        custom = words[4:] if version == 0 else words[5:]
        if flags & ~0x0F:
            raise ValueError(f"DT entry {index} has unrecognized flags")
        compression = flags & 0x0F
        if compression >= len(COMPRESSION_NAMES):
            raise ValueError(f"DT entry {index} has unsupported compression")
        if size < 1 or location < metadata_end or location + size > total:
            raise ValueError(f"DT entry {index} outside declared image bounds")
        payload = data[location:location + size]
        decoded = _inflate_entry(payload, compression, index)
        fdt = parse_fdt(decoded)
        if any(decoded[len(fdt):]):
            raise ValueError(f"DT entry {index} contains nonzero trailing data")
        item = {
            "index": index, "id": board_id, "revision": revision,
            "table_version": version, "entry_flags": flags,
            "compression": COMPRESSION_NAMES[compression],
            "custom_fields": list(custom),
            "table_page_size": page_size, "fdt": fdt,
        }
        entries.append(item if with_metadata else
                       (index, board_id, revision, fdt))
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
    entries = parse_android_dtbo(data, with_metadata=True)
    if not shutil.which("dtc"):
        raise RuntimeError("dtc is required to inspect FDT properties")
    output.mkdir(parents=True, exist_ok=True)
    from audit_xiaomi_panel_evidence import panel_evidence_from_fdt
    results = []
    for entry in entries:
        index = entry["index"]
        fdt = entry["fdt"]
        proc = subprocess.run(["dtc", "-q", "-I", "dtb", "-O", "dts"],
                              input=fdt, capture_output=True, check=True)
        decoded = proc.stdout.decode("utf-8", errors="replace")
        record = {
            "entry_index": index,
            "entry_id": entry["id"],
            "entry_revision": entry["revision"],
            "entry_custom_fields": entry["custom_fields"],
            "table_version": entry["table_version"],
            "entry_flags": entry["entry_flags"],
            "entry_compression": entry["compression"],
            "table_page_size": entry["table_page_size"],
            "dtb_sha256": hashlib.sha256(fdt).hexdigest(),
            "candidate_signals": inspect_dts(decoded),
            "manufacturer_panel_structure": panel_evidence_from_fdt(fdt),
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

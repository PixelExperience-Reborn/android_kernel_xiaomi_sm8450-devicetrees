#!/usr/bin/env python3
"""Audit a Xiaomi mondrian stock Fastboot .tgz without extracting other partitions.

The archive is local input from Xiaomi's distribution channel. A matching
user-supplied checksum is *integrity*, not independent manufacturer authenticity.
Nothing extracted is committed to the device tree or made flashable.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tarfile
import tempfile

from audit_xiaomi_stock_dtbo import audit
from audit_xiaomi_vendor_boot import audit_vendor_boot_data, MAX_VENDOR_BOOT_BYTES

MAX_DTBO_BYTES = 128 * 1024 * 1024
CHUNK = 1024 * 1024


def sha256_file(path):
    checksum = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(CHUNK), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def read_mondrian_boot_partitions(archive_path):
    """Find stock DTBO (required) and vendor_boot (optional), in one tar stream.

    Values are (archive path, raw bounded bytes). All other partitions are
    ignored; no extracted filename or archive link ever reaches the filesystem.
    """
    found = {}
    stock_root = None
    limits = {"dtbo.img": MAX_DTBO_BYTES,
              "vendor_boot.img": MAX_VENDOR_BOOT_BYTES}
    try:
        with tarfile.open(archive_path, mode="r|gz") as source:
            for member in source:
                name = member.name
                path = PurePosixPath(name)
                if path.is_absolute() or ".." in path.parts or "\\" in name:
                    raise ValueError(f"unsafe archive member path: {name!r}")
                if len(path.parts) < 3 or path.parts[-2] != "images":
                    continue
                basename = path.parts[-1]
                if basename not in limits:
                    continue
                if not path.parts[0].startswith("mondrian_"):
                    raise ValueError("DTBO/vendor_boot not under a mondrian firmware root")
                if "_images_" not in path.parts[0]:
                    raise ValueError("input archive does not identify a mondrian Fastboot ROM")
                if len(path.parts) != 3:
                    raise ValueError("DTBO/vendor_boot is outside the stock images directory")
                if stock_root is None:
                    stock_root = path.parts[0]
                elif path.parts[0] != stock_root:
                    raise ValueError("mixed mondrian Fastboot roots or regional SKU packages")
                if not member.isfile():
                    raise ValueError(f"{basename} archive member is not a regular file")
                if basename in found:
                    raise ValueError(f"multiple {basename} members in stock archive")
                limit = limits[basename]
                if not 40 <= member.size <= limit:
                    raise ValueError(f"{basename} archive member size outside safe limits")
                handle = source.extractfile(member)
                if handle is None:
                    raise ValueError(f"{basename} archive member cannot be read")
                data = handle.read(limit + 1)
                if len(data) != member.size:
                    raise ValueError(f"{basename} archive payload length mismatch")
                found[basename] = (name, data)
    except (tarfile.TarError, EOFError) as exc:
        raise ValueError(f"invalid Xiaomi Fastboot archive: {exc}") from exc
    if "dtbo.img" not in found:
        raise ValueError("no images/dtbo.img in mondrian stock Fastboot archive")
    return found


def read_mondrian_dtbo(archive_path):
    """Compatibility wrapper for existing tests and DTBO-only users."""
    return read_mondrian_boot_partitions(archive_path)["dtbo.img"]


def audit_fastboot_package(package, expected_sha256, output):
    if not package.is_file():
        raise ValueError("local Xiaomi stock Fastboot package not found")
    if (len(expected_sha256) != 64
            or any(c not in "0123456789abcdefABCDEF" for c in expected_sha256)):
        raise ValueError("expected stock package SHA256 must have 64 hex digits")
    actual = sha256_file(package)
    if actual != expected_sha256.lower():
        raise ValueError("manufacturer source-package checksum mismatch")
    partitions = read_mondrian_boot_partitions(package)
    member_path, dtbo_data = partitions["dtbo.img"]
    # All analyses must succeed before anything is published to the output
    # folder. A malformed vendor_boot must not leave a stale partial DTBO
    # report that could be mistaken for completed manufacturer evidence.
    with tempfile.TemporaryDirectory(prefix="pe-mondrian-stock-") as work:
        work_path = Path(work)
        extracted = work_path / "dtbo.img"
        extracted.write_bytes(dtbo_data)
        result_path = audit(extracted, package_sha256=actual, output=work_path)
        evidence = json.loads(result_path.read_text())
    if "vendor_boot.img" in partitions:
        vendor_member, vendor_data = partitions["vendor_boot.img"]
        evidence["stock_vendor_boot"] = audit_vendor_boot_data(vendor_data)
        evidence["stock_vendor_boot"]["fastboot_archive_member"] = vendor_member
    else:
        evidence["stock_vendor_boot"] = {
            "present": False,
            "status": "NO_VENDOR_BOOT_IN_ARCHIVE",
            "m11a_panel_ready": False,
        }
    evidence.update({
        "fastboot_archive_filename": package.name,
        "fastboot_archive_member": member_path,
        "fastboot_archive_sha256_verified_against_user_expected": True,
        "fastboot_archive_is_xiaomi_stock_independently_authenticated": False,
        "manufacturer_panel_parameters_verified": False,
        "m11a_product_selection_allowed": False,
    })
    # Publish one complete diagnostic report, atomically replacing any prior
    # result only after both partitions and the archive pass validation.
    output.mkdir(parents=True, exist_ok=True)
    final_report = output / "xiaomi-stock-dtbo-diagnostic.json"
    temporary_report = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output,
            prefix=".mondrian-audit-", suffix=".tmp", delete=False,
        ) as stream:
            temporary_report = Path(stream.name)
            json.dump(evidence, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_report, final_report)
    finally:
        if temporary_report is not None:
            temporary_report.unlink(missing_ok=True)
    return final_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fastboot-tgz", type=Path, required=True,
                        help="local Xiaomi mondrian stock .tgz Fastboot archive")
    parser.add_argument("--expected-sha256", required=True,
                        help="full archive SHA256 independently recorded before audit")
    parser.add_argument("--out", type=Path, required=True,
                        help="output directory for JSON-only diagnostic evidence")
    args = parser.parse_args()
    try:
        output = audit_fastboot_package(
            args.fastboot_tgz, args.expected_sha256, args.out)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    print(f"[PASS] Xiaomi Fastboot archive integrity and DTBO analysis: {output}")
    print("[BLOCKED] OEM authenticity, M11A panel commands and runtime remain unverified")


if __name__ == "__main__":
    main()

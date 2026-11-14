#!/usr/bin/env python3
"""Audit a Xiaomi mondrian stock Fastboot .tgz without extracting other partitions.

The archive is local input from Xiaomi's distribution channel. A matching
user-supplied checksum is *integrity*, not independent manufacturer authenticity.
Nothing extracted is committed to the device tree or made flashable.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
import tempfile

from audit_xiaomi_stock_dtbo import audit

MAX_DTBO_BYTES = 128 * 1024 * 1024
CHUNK = 1024 * 1024


def sha256_file(path):
    checksum = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(CHUNK), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def read_mondrian_dtbo(archive_path):
    """Read exactly one normal-file images/dtbo.img from a mondrian Fastboot tar.

    Returns the archive member's original name and its bytes. All other members
    are skipped; never use tarfile.extract/extractall on an untrusted archive.
    """
    candidate = None
    try:
        with tarfile.open(archive_path, mode="r|gz") as source:
            for member in source:
                name = member.name
                path = PurePosixPath(name)
                if path.is_absolute() or ".." in path.parts or "\\" in name:
                    raise ValueError(f"unsafe archive member path: {name!r}")
                if path.parts[-2:] != ("images", "dtbo.img"):
                    continue
                if not path.parts or not path.parts[0].startswith("mondrian"):
                    raise ValueError("DTBO is not under the mondrian firmware root")
                if "_images_" not in path.parts[0]:
                    raise ValueError("input archive does not identify a mondrian Fastboot ROM")
                if not member.isfile():
                    raise ValueError("DTBO archive member is not a regular file")
                if candidate is not None:
                    raise ValueError("multiple dtbo.img members in stock archive")
                if not 40 <= member.size <= MAX_DTBO_BYTES:
                    raise ValueError("DTBO archive member size outside safe limits")
                handle = source.extractfile(member)
                if handle is None:
                    raise ValueError("DTBO archive member cannot be read")
                data = handle.read(MAX_DTBO_BYTES + 1)
                if len(data) != member.size:
                    raise ValueError("DTBO archive payload length mismatch")
                candidate = (name, data)
    except (tarfile.TarError, EOFError) as exc:
        raise ValueError(f"invalid Xiaomi Fastboot archive: {exc}") from exc
    if candidate is None:
        raise ValueError("no images/dtbo.img in mondrian stock Fastboot archive")
    return candidate


def audit_fastboot_package(package, expected_sha256, output):
    if not package.is_file():
        raise ValueError("local Xiaomi stock Fastboot package not found")
    if (len(expected_sha256) != 64
            or any(c not in "0123456789abcdefABCDEF" for c in expected_sha256)):
        raise ValueError("expected stock package SHA256 must have 64 hex digits")
    actual = sha256_file(package)
    if actual != expected_sha256.lower():
        raise ValueError("manufacturer source-package checksum mismatch")
    member_path, dtbo_data = read_mondrian_dtbo(package)
    output.mkdir(parents=True, exist_ok=True)
    # Existing DTBO audit accepts a local path; use a disposable file outside
    # the repo and remove the raw OEM image after obtaining JSON evidence.
    with tempfile.TemporaryDirectory(prefix="pe-mondrian-stock-") as work:
        extracted = Path(work) / "dtbo.img"
        extracted.write_bytes(dtbo_data)
        result_path = audit(extracted, package_sha256=actual, output=output)
    evidence = json.loads(result_path.read_text())
    evidence.update({
        "fastboot_archive_filename": package.name,
        "fastboot_archive_member": member_path,
        "fastboot_archive_sha256_verified_against_user_expected": True,
        "fastboot_archive_is_xiaomi_stock_independently_authenticated": False,
        "manufacturer_panel_parameters_verified": False,
        "m11a_product_selection_allowed": False,
    })
    result_path.write_text(json.dumps(evidence, indent=2) + "\n")
    return result_path


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

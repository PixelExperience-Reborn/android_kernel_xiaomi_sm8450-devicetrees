#!/usr/bin/env python3
"""Read-only diagnostic of a mondrian CURRENT-partition collection archive.

This is NOT a Xiaomi stock Fastboot/OTA audit. Only the current boot slot was
copied; a custom ROM may have replaced either image. No flashing, unpacking
onto disk, DTS generation, sensor selection or product approval takes place.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tempfile

from audit_xiaomi_stock_dtbo import parse_android_dtbo
from audit_xiaomi_panel_evidence import panel_evidence_from_fdt
from audit_xiaomi_camera_evidence import camera_flash_evidence_from_fdt
from audit_xiaomi_vendor_boot import audit_vendor_boot_data, MAX_VENDOR_BOOT_BYTES

MAX_DTBO_BYTES = 128 * 1024 * 1024
MAX_TEXT_BYTES = 8192
EXPECTED_FILES = frozenset({
    'metadata.txt', 'README.txt', 'sha256sums.txt',
    'dtbo.img', 'vendor_boot.img', 'dtbo.dd.log', 'vendor_boot.dd.log',
})
DIRECTORY = re.compile(r'mondrian_readonly_evidence_[0-9]{8}_[0-9]{6}')
DIGEST = re.compile(r'([0-9a-fA-F]{64})  (dtbo|vendor_boot)\.img')
SIZES = {'dtbo.img': MAX_DTBO_BYTES,
         'vendor_boot.img': MAX_VENDOR_BOOT_BYTES}


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _archive_sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read_archive(path):
    """Stream whitelisted files into bounded memory; never extract tar paths."""
    found = {}
    directory = None
    try:
        with tarfile.open(path, mode='r|gz') as archive:
            for member in archive:
                name = member.name
                pp = PurePosixPath(name)
                if pp.is_absolute() or '..' in pp.parts or '\\' in name:
                    raise ValueError('unsafe archive path')
                if not pp.parts or not DIRECTORY.fullmatch(pp.parts[0]):
                    raise ValueError('unexpected mondrian collection root')
                if directory is None:
                    directory = pp.parts[0]
                if pp.parts[0] != directory:
                    raise ValueError('mixed collection directories')
                if len(pp.parts) == 1 and member.isdir():
                    continue
                if (len(pp.parts) != 2 or pp.parts[1] not in EXPECTED_FILES
                        or not member.isfile()):
                    raise ValueError('unexpected/nonregular collection member')
                leaf = pp.parts[1]
                if leaf in found:
                    raise ValueError('duplicate archive member: ' + leaf)
                limit = SIZES.get(leaf, MAX_TEXT_BYTES)
                if not 0 < member.size <= limit:
                    raise ValueError('oversized/empty archive member: ' + leaf)
                stream = archive.extractfile(member)
                if stream is None:
                    raise ValueError('missing archive payload: ' + leaf)
                data = stream.read(limit + 1)
                if len(data) != member.size:
                    raise ValueError('truncated archive payload: ' + leaf)
                found[leaf] = data
    except (tarfile.TarError, EOFError) as exc:
        raise ValueError('malformed collection archive') from exc
    if not {'metadata.txt', 'sha256sums.txt'} <= found.keys():
        raise ValueError('collection metadata/checksums missing')
    if not any(name in found for name in SIZES):
        raise ValueError('no current boot partition image collected')
    return found


def verify_collection(files):
    """Check collection *internal* consistency, never vendor authenticity."""
    try:
        lines = files['metadata.txt'].decode('utf-8', 'strict').splitlines()
        pairs = [line.split('=', 1) for line in lines]
        if any(len(p) != 2 for p in pairs):
            raise ValueError('malformed collection metadata')
        metadata = dict(pairs)
        if len(metadata) != len(pairs):
            raise ValueError('duplicate collection metadata key')
        checksums = files['sha256sums.txt'].decode('ascii', 'strict').splitlines()
    except UnicodeError as exc:
        raise ValueError('non-textual collection metadata/checksums') from exc
    if (metadata.get('report_type') != 'mondrian_current_partition_readonly_evidence'
            or metadata.get('original_xiaomi_stock_provenance_verified') != 'false'):
        raise ValueError('not a read-only current-partition collection')
    if (metadata.get('ro.product.device') != 'mondrian'
            and metadata.get('ro.boot.product.device') != 'mondrian'):
        raise ValueError('not confirmed as mondrian userspace')
    slot = metadata.get('ro.boot.slot_suffix')
    if slot not in ('', '_a', '_b'):
        raise ValueError('unsupported active slot suffix')
    images = {name for name in SIZES if name in files}
    declared = {}
    for line in checksums:
        match = DIGEST.fullmatch(line)
        if match is None:
            raise ValueError('unexpected sha256sums.txt entry')
        name = match[2] + '.img'
        if name in declared:
            raise ValueError('duplicate partition checksum')
        declared[name] = match[1].lower()
    if images != set(declared):
        raise ValueError('partition list does not match checksum manifest')
    for name in images:
        if _sha(files[name]) != declared[name]:
            raise ValueError('checksum mismatch: ' + name)
    return metadata


def audit_current_partitions(archive_path):
    """Read evidence from current ROM only; return a JSON-serializable report."""
    if not archive_path.is_file():
        raise ValueError('collection archive not found')
    files = read_archive(archive_path)
    meta = verify_collection(files)
    report = {
        'schema_version': 1,
        'device': 'mondrian',
        'android_base_target': 'PixelExperience-Reborn AOSP 17',
        'source': 'current_active_boot_slot_partitions_NOT_Xiaomi_stock',
        'collection_archive_sha256': _archive_sha(archive_path),
        'internal_sha256_consistency_verified': True,
        'xiaomi_stock_provenance_verified': False,
        'current_rom_may_be_custom': True,
        'boot_slot_reported_by_userspace': meta['ro.boot.slot_suffix'],
        'android_release_reported_by_userspace': meta.get('ro.build.version.release'),
        'android_sdk_reported_by_userspace': meta.get('ro.build.version.sdk'),
        'camera_sensor_identification_verified': False,
        'camera_cci_csi_wiring_verified': False,
        'camera_regulator_power_sequences_verified': False,
        'camera_flash_channel_verified': False,
        'camera_hal_qualified': False,
        'physical_camera_tested': False,
        'production_camera_dtbo_approved': False,
        'production_boot_vendor_boot_approved': False,
        'status': 'DIAGNOSTIC_ONLY_CURRENT_ROM_NOT_MANUFACTURER_EVIDENCE',
    }
    if 'dtbo.img' in files:
        image = files['dtbo.img']
        entries = parse_android_dtbo(image, with_metadata=True)
        report['current_dtbo'] = {
            'present': True,
            'sha256': _sha(image),
            'bytes': len(image),
            'entries': [{
                'index': item['index'],
                'board_id_raw': item['id'],
                'revision_raw': item['revision'],
                'table_version': item['table_version'],
                'entry_flags': item['entry_flags'],
                'dtb_sha256': _sha(item['fdt']),
                'camera_flash_candidates': camera_flash_evidence_from_fdt(item['fdt']),
                'panel_candidates': panel_evidence_from_fdt(item['fdt']),
            } for item in entries],
            'bootloader_selection_verified': False,
        }
    else:
        report['current_dtbo'] = {'present': False}
    if 'vendor_boot.img' in files:
        image = files['vendor_boot.img']
        report['current_vendor_boot'] = audit_vendor_boot_data(image)
        report['current_vendor_boot']['source'] = 'current_active_partition_NOT_stock'
    else:
        report['current_vendor_boot'] = {'present': False}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True,
                        help='archive produced by collect_mondrian_hardware_evidence.sh')
    parser.add_argument('--out', type=Path, required=True,
                        help='local directory for JSON report only; raw images not written')
    args = parser.parse_args()
    try:
        report = audit_current_partitions(args.archive)
        args.out.mkdir(parents=True, exist_ok=True)
        target = args.out / 'mondrian-current-partitions-camera-diagnostic.json'
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                    mode='w', encoding='utf-8', dir=args.out,
                    prefix='.mondrian-current-', suffix='.tmp',
                    delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(report, stream, indent=2)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    except (ValueError, OSError, RuntimeError,
            subprocess.CalledProcessError) as exc:
        parser.error(str(exc))
    print('[PASS] Current mondrian boot-partition structures: ' + str(target))
    print('[BLOCKED] Xiaomi stock provenance, Camera sensor wiring, PMIC channels and hardware approval')


if __name__ == '__main__':
    main()

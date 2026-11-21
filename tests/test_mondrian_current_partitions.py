"""No real boot images: current-partition archive policy and integrity tests."""
import hashlib
import io
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from audit_mondrian_current_partitions import audit_current_partitions, read_archive

FOLDER = 'mondrian_readonly_evidence_20261119_160807'
DTBO = b'pretend-dtbo-table-for-test-only'
VENDOR = b'pretend-vendor-boot-for-test-only'


def standard_files():
    meta = ('report_type=mondrian_current_partition_readonly_evidence\n'
            'original_xiaomi_stock_provenance_verified=false\n'
            'ro.product.device=mondrian\n'
            'ro.boot.product.device=mondrian\n'
            'ro.boot.slot_suffix=_a\n'
            'ro.build.version.release=17\n'
            'ro.build.version.sdk=37\n')
    hashes = ''.join(hashlib.sha256(data).hexdigest() + '  ' + name + '\n'
                     for name, data in [('dtbo.img', DTBO),
                                        ('vendor_boot.img', VENDOR)])
    return {'metadata.txt': meta.encode(), 'sha256sums.txt': hashes.encode(),
            'README.txt': b'CURRENT ACTIVE PARTITIONS; NOT ORIGINAL OEM\n',
            'dtbo.img': DTBO, 'vendor_boot.img': VENDOR}


def make_tar(path, files, *, extra=None):
    with tarfile.open(path, mode='w:gz') as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(FOLDER + '/' + name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        if extra is not None:
            name, data = extra
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))


class CurrentPartitionCollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.archive = Path(self.temp.name) / 'evidence.tar.gz'

    def test_candidate_report_cannot_authorize_camera_even_if_parsers_find_nodes(self):
        make_tar(self.archive, standard_files())
        fdt = b'fixture-fdt'
        with (patch('audit_mondrian_current_partitions.parse_android_dtbo',
                    return_value=[{'index': 0, 'id': 25, 'revision': 1,
                                   'table_version': 0, 'entry_flags': 0,
                                   'fdt': fdt}]),
              patch('audit_mondrian_current_partitions.camera_flash_evidence_from_fdt',
                    return_value={'camera_flash_node_count': 3}),
              patch('audit_mondrian_current_partitions.panel_evidence_from_fdt',
                    return_value={'mentions_m11a': True}),
              patch('audit_mondrian_current_partitions.audit_vendor_boot_data',
                    return_value={'present': True, 'embedded_dtb_count': 2})):
            report = audit_current_partitions(self.archive)
        self.assertEqual(report['source'],
                         'current_active_boot_slot_partitions_NOT_Xiaomi_stock')
        self.assertTrue(report['internal_sha256_consistency_verified'])
        self.assertFalse(report['xiaomi_stock_provenance_verified'])
        self.assertFalse(report['production_camera_dtbo_approved'])
        self.assertFalse(report['camera_flash_channel_verified'])
        self.assertFalse(report['physical_camera_tested'])
        self.assertEqual(report['current_dtbo']['entries'][0][
            'camera_flash_candidates']['camera_flash_node_count'], 3)
        self.assertFalse(report['current_dtbo']['bootloader_selection_verified'])
        self.assertEqual(report['current_vendor_boot']['source'],
                         'current_active_partition_NOT_stock')
        self.assertEqual(report['boot_slot_reported_by_userspace'], '_a')

    def test_corrupt_dtbo_hash_is_rejected_before_parsing(self):
        files = standard_files()
        files['dtbo.img'] = b'changed-current-partition'
        make_tar(self.archive, files)
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            audit_current_partitions(self.archive)

    def test_wrong_device_is_rejected(self):
        files = standard_files()
        files['metadata.txt'] = (files['metadata.txt'].replace(
            b'ro.product.device=mondrian', b'ro.product.device=uke').replace(
            b'ro.boot.product.device=mondrian', b'ro.boot.product.device=uke'))
        make_tar(self.archive, files)
        with self.assertRaisesRegex(ValueError, 'not confirmed as mondrian'):
            audit_current_partitions(self.archive)

    def test_stock_provenance_claim_is_rejected(self):
        files = standard_files()
        files['metadata.txt'] = files['metadata.txt'].replace(
            b'original_xiaomi_stock_provenance_verified=false',
            b'original_xiaomi_stock_provenance_verified=true')
        make_tar(self.archive, files)
        with self.assertRaisesRegex(ValueError, 'not a read-only'):
            audit_current_partitions(self.archive)

    def test_duplicate_checksum_rejected(self):
        files = standard_files()
        files['sha256sums.txt'] += files['sha256sums.txt'].splitlines(True)[0]
        make_tar(self.archive, files)
        with self.assertRaisesRegex(ValueError, 'duplicate partition checksum'):
            audit_current_partitions(self.archive)

    def test_archive_traversal_rejected_without_extracting_anything(self):
        make_tar(self.archive, standard_files(),
                 extra=(FOLDER + '/../escape', b'unsafe'))
        with self.assertRaisesRegex(ValueError, 'unsafe archive path'):
            read_archive(self.archive)
        self.assertFalse((Path(self.temp.name) / 'escape').exists())

    def test_archive_symlink_rejected(self):
        with tarfile.open(self.archive, mode='w:gz') as archive:
            link = tarfile.TarInfo(FOLDER + '/dtbo.img')
            link.type = tarfile.SYMTYPE
            link.linkname = '/dev/block/by-name/dtbo_a'
            archive.addfile(link)
        with self.assertRaisesRegex(ValueError, 'unexpected/nonregular'):
            read_archive(self.archive)

    def test_missing_vendor_boot_is_diagnostic_only(self):
        files = standard_files()
        files.pop('vendor_boot.img')
        files['sha256sums.txt'] = files['sha256sums.txt'].splitlines(True)[0]
        make_tar(self.archive, files)
        with (patch('audit_mondrian_current_partitions.parse_android_dtbo',
                    return_value=[]),
              patch('audit_mondrian_current_partitions.audit_vendor_boot_data') as vendor):
            result = audit_current_partitions(self.archive)
        vendor.assert_not_called()
        self.assertFalse(result['current_vendor_boot']['present'])
        self.assertFalse(result['production_boot_vendor_boot_approved'])

    def test_empty_image_and_missing_manifest_rejected(self):
        for case in ('empty', 'missing'):
            with self.subTest(case=case):
                files = standard_files()
                if case == 'empty':
                    files['vendor_boot.img'] = b''
                else:
                    files.pop('sha256sums.txt')
                make_tar(self.archive, files)
                with self.assertRaises(ValueError):
                    read_archive(self.archive) if case == 'empty' else audit_current_partitions(self.archive)


if __name__ == '__main__':
    unittest.main()

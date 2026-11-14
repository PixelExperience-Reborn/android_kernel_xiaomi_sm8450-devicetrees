"""Regression checks: accept only a Xiaomi mondrian Fastboot DTBO, never a ROM tree."""
from io import BytesIO
import hashlib
import json
import struct
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from audit_xiaomi_fastboot_package import (  # noqa: E402
    audit_fastboot_package, read_mondrian_dtbo, sha256_file,
)

STOCK_ROOT = "mondrian_global_images_OS3.0.5.0.VMNMIXM_TEST_15.0_global"
STOCK_MEMBER = STOCK_ROOT + "/images/dtbo.img"


def fake_dtb():
    """Structural test fixture, NOT Xiaomi manufacturer panel/DTBO data."""
    return struct.pack(">10I", 0xD00DFEED, 40, 40, 40, 40, 17, 16, 0, 0, 0)


def tar_package(path, entries):
    """Write a tiny synthetic .tgz; entries (member_name, content_or_None)."""
    with tarfile.open(path, mode="w:gz") as dest:
        for name, data in entries:
            info = tarfile.TarInfo(name)
            if data is None:
                info.type = tarfile.SYMTYPE
                info.linkname = "other-dtbo.img"
                dest.addfile(info)
            else:
                info.size = len(data)
                dest.addfile(info, BytesIO(data))


class XiaomiFastbootAuditTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.package = Path(self.work.name) / "mondrian-test.tgz"

    def test_read_only_expected_dtbo_member(self):
        tar_package(self.package, [
            (STOCK_ROOT + "/flash_all.sh", b"synthetic-test"),
            (STOCK_MEMBER, fake_dtb()),
            (STOCK_ROOT + "/images/boot.img", b"do not extract"),
        ])
        name, data = read_mondrian_dtbo(self.package)
        self.assertEqual(name, STOCK_MEMBER)
        self.assertEqual(data, fake_dtb())
        self.assertEqual(sha256_file(self.package),
                         hashlib.sha256(self.package.read_bytes()).hexdigest())

    def test_reject_wrong_root(self):
        tar_package(self.package, [("otherdevice_images_TEST/images/dtbo.img", fake_dtb())])
        with self.assertRaisesRegex(ValueError, "mondrian"):
            read_mondrian_dtbo(self.package)

    def test_reject_not_fastboot_layout(self):
        tar_package(self.package, [("mondrian_recovery/images/dtbo.img", fake_dtb())])
        with self.assertRaisesRegex(ValueError, "Fastboot"):
            read_mondrian_dtbo(self.package)

    def test_reject_archive_with_no_dtbo(self):
        tar_package(self.package, [(STOCK_ROOT + "/images/boot.img", b"not a dtbo")])
        with self.assertRaisesRegex(ValueError, "no images/dtbo.img"):
            read_mondrian_dtbo(self.package)

    def test_reject_symlinked_dtbo(self):
        tar_package(self.package, [(STOCK_MEMBER, None)])
        with self.assertRaisesRegex(ValueError, "regular file"):
            read_mondrian_dtbo(self.package)

    def test_reject_duplicate_dtbo(self):
        tar_package(self.package, [(STOCK_MEMBER, fake_dtb()), (STOCK_MEMBER, fake_dtb())])
        with self.assertRaisesRegex(ValueError, "multiple dtbo.img"):
            read_mondrian_dtbo(self.package)

    def test_reject_path_traversal(self):
        tar_package(self.package, [(STOCK_ROOT + "/../images/dtbo.img", fake_dtb())])
        with self.assertRaisesRegex(ValueError, "unsafe archive member"):
            read_mondrian_dtbo(self.package)

    def test_reject_short_dtbo_payload(self):
        tar_package(self.package, [(STOCK_MEMBER, b"short")])
        with self.assertRaisesRegex(ValueError, "safe limits"):
            read_mondrian_dtbo(self.package)

    def test_refuse_unmatched_archive_sha256(self):
        tar_package(self.package, [(STOCK_MEMBER, fake_dtb())])
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            audit_fastboot_package(self.package, "0" * 64, Path(self.work.name) / "out")

    def test_audit_metadata_does_not_certify_manufacturer_or_release(self):
        tar_package(self.package, [(STOCK_MEMBER, fake_dtb())])
        dest = Path(self.work.name) / "evidence"

        def mock_audit(image, *, package_sha256, output):
            self.assertEqual(image.read_bytes(), fake_dtb())
            self.assertEqual(package_sha256, sha256_file(self.package))
            result = output / "xiaomi-stock-dtbo-diagnostic.json"
            result.write_text(json.dumps({
                "status": "DIAGNOSTIC_ONLY_NOT_FOR_FLASHING",
                "source_authenticity_independently_verified": False,
                "m11a_panel_ready": False,
            }))
            return result

        with patch("audit_xiaomi_fastboot_package.audit", side_effect=mock_audit):
            result = audit_fastboot_package(self.package, sha256_file(self.package), dest)
        metadata = json.loads(result.read_text())
        self.assertEqual(metadata["fastboot_archive_member"], STOCK_MEMBER)
        self.assertTrue(metadata["fastboot_archive_sha256_verified_against_user_expected"])
        self.assertFalse(metadata["fastboot_archive_is_xiaomi_stock_independently_authenticated"])
        self.assertFalse(metadata["manufacturer_panel_parameters_verified"])
        self.assertFalse(metadata["m11a_product_selection_allowed"])
        self.assertFalse(list(dest.glob("*.img")))


if __name__ == "__main__":
    unittest.main()

"""Synthetic FDT v17 structural and panel audit, not manufacturer panel data."""
import json
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from audit_xiaomi_panel_evidence import (  # noqa: E402
    _mode_validation, fdt_nodes, panel_evidence_from_fdt,
)


class FdtBuilder:
    """Minimal standards-conforming FDT v17 fixture, with synthetic values."""

    def __init__(self):
        self.strings = bytearray()
        self.name_offsets = {}
        self.structure = bytearray()

    def tag(self, number):
        self.structure.extend(struct.pack(">I", number))

    def name(self, value):
        if value not in self.name_offsets:
            self.name_offsets[value] = len(self.strings)
            self.strings.extend(value.encode() + b"\x00")
        return self.name_offsets[value]

    def begin(self, name):
        self.tag(1)
        self.structure.extend(name.encode() + b"\x00")
        self.structure.extend(b"\x00" * (-len(self.structure) % 4))

    def end(self):
        self.tag(2)

    def prop(self, name, value):
        self.tag(3)
        self.structure.extend(struct.pack(">2I", len(value), self.name(name)))
        self.structure.extend(value)
        self.structure.extend(b"\x00" * (-len(self.structure) % 4))

    def string(self, name, value):
        self.prop(name, value.encode() + b"\x00")

    def cells(self, name, *values):
        self.prop(name, struct.pack(">" + "I" * len(values), *values))

    def build(self):
        self.tag(9)
        hdr = 40
        reserve = b"\x00" * 16
        struct_offset = hdr + len(reserve)
        strings_offset = struct_offset + len(self.structure)
        total = strings_offset + len(self.strings)
        header = struct.pack(">10I", 0xD00DFEED, total,
                             struct_offset, strings_offset, hdr,
                             17, 16, 0, len(self.strings),
                             len(self.structure))
        return header + reserve + bytes(self.structure) + bytes(self.strings)


def sample_panel_fdt(*, slice_width=500, outside_hbm=False,
                     chroma_format=None):
    dt = FdtBuilder()
    dt.begin("")
    dt.begin("soc")
    if outside_hbm:
        dt.begin("other-display")
        dt.prop("mi,local-hbm-enabled", b"")
        dt.end()
    dt.begin("panel@0")
    dt.string("qcom,mdss-dsi-panel-name", "synthetic test panel")
    dt.string("qcom,mdss-dsi-panel-type", "dsi_cmd_mode")
    dt.cells("mi,panel-id", 0x12345678, 0x00000001)
    dt.cells("qcom,mdss-dsi-bl-max-level", 4095)
    dt.prop("mi,local-hbm-enabled", b"")
    dt.prop("qcom,mdss-dsi-on-command", b"\xDE\xAD\xBE\xEF" * 7)
    dt.begin("qcom,mdss-dsi-display-timings")
    dt.begin("timing@0")
    dt.cells("qcom,mdss-dsi-panel-framerate", 60)
    dt.cells("qcom,mdss-dsi-panel-width", 1000)
    dt.cells("qcom,mdss-dsi-panel-height", 2000)
    dt.string("qcom,compression-mode", "dsc")
    if chroma_format is not None:
        dt.cells("qcom,src-chroma-format", chroma_format)
    dt.cells("qcom,mdss-dsc-version", 0x12)
    dt.cells("qcom,mdss-dsc-slice-width", slice_width)
    dt.cells("qcom,mdss-dsc-slice-height", 32)
    dt.cells("qcom,mdss-dsc-slice-per-pkt", 2)
    dt.cells("qcom,mdss-dsc-bit-per-component", 10)
    dt.cells("qcom,mdss-dsc-bit-per-pixel", 8)
    dt.end()
    dt.end()
    dt.end()
    dt.end()
    dt.end()
    return dt.build()


def with_synthetic_memreserve(fdt, entries):
    """Replace the standard zero reservation map and adjust FDT offsets."""
    raw = bytearray(fdt)
    replacement = b"".join(struct.pack(">QQ", address, size)
                           for address, size in entries)
    delta = len(replacement) - 16
    raw[40:56] = replacement
    for header_offset in (4, 8, 12):  # totalsize, struct, strings
        struct.pack_into(">I", raw, header_offset,
                         struct.unpack_from(">I", raw, header_offset)[0] + delta)
    return bytes(raw)


class ManufacturerPanelEvidenceTests(unittest.TestCase):
    def test_read_numeric_panel_and_dsc_properties_without_command_payload(self):
        blob = sample_panel_fdt()
        output = panel_evidence_from_fdt(blob)
        self.assertEqual(output["panel_candidate_count"], 1)
        panel = output["panel_candidates"][0]
        self.assertEqual(panel["panel_name"], "synthetic test panel")
        self.assertEqual(panel["xiaomi_panel_id_hex"], ["12345678", "00000001"])
        self.assertEqual(panel["backlight_max_level"], 4095)
        self.assertTrue(panel["xiaomi_local_hbm_property_present"])
        self.assertTrue(panel["panel_command_sequences_present"])
        mode = panel["modes"][0]
        self.assertEqual(mode["refresh_hz"], 60)
        self.assertEqual(mode["width_px"], 1000)
        self.assertEqual(mode["dsc_slice_width"], 500)
        self.assertEqual(mode["dsc_slice_height"], 32)
        self.assertEqual(mode["dsc_version"], 0x12)
        self.assertTrue(mode["basic_geometry_and_dsc_valid"])
        self.assertFalse(mode["physical_panel_validated"])
        self.assertFalse(output["production_panel_dts_approved"])
        self.assertNotIn("deadbeef", json.dumps(output).lower())


    @staticmethod
    def _valid_qualcomm_dsc_mode():
        return {
            "compression_mode": "dsc",
            "refresh_hz": 120,
            "width_px": 1440,
            "height_px": 3200,
            "dsc_version": 0x12,
            "dsc_scr_version": 0,
            "dsc_slice_width": 720,
            "dsc_slice_height": 32,
            "dsc_slices_per_packet": 2,
            "dsc_bits_per_component": 10,
            "dsc_bits_per_pixel": 8,
        }

    def test_valid_qualcomm_dsc_geometry_does_not_qualify_panel(self):
        self.assertTrue(_mode_validation(self._valid_qualcomm_dsc_mode()))

    def test_reject_one_line_dsc_slice_before_kernel_divide(self):
        mode = self._valid_qualcomm_dsc_mode()
        for height in (0, 1, 3201):
            with self.subTest(height=height):
                mode["dsc_slice_height"] = height
                self.assertFalse(_mode_validation(mode))

    def test_reject_unsupported_bpc_from_qualcomm_rate_tables(self):
        mode = self._valid_qualcomm_dsc_mode()
        for bpc in (1, 6, 12, 16):
            with self.subTest(bpc=bpc):
                mode["dsc_bits_per_component"] = bpc
                self.assertFalse(_mode_validation(mode))
        for bpc in (8, 10):
            with self.subTest(accepted_bpc=bpc):
                mode["dsc_bits_per_component"] = bpc
                self.assertTrue(_mode_validation(mode))

    def test_reject_unsupported_bpp_from_qualcomm_rate_tables(self):
        mode = self._valid_qualcomm_dsc_mode()
        for bpp in (0, 5, 9, 11, 24, 64):
            with self.subTest(bpp=bpp):
                mode["dsc_bits_per_pixel"] = bpp
                self.assertFalse(_mode_validation(mode))

    def test_reject_unsupported_dsc_version_and_scr_revision(self):
        mode = self._valid_qualcomm_dsc_mode()
        for version in (0x10, 0x13, 0x21, 0):
            with self.subTest(version=version):
                mode["dsc_version"] = version
                self.assertFalse(_mode_validation(mode))
        mode = self._valid_qualcomm_dsc_mode()
        for scr in (2, 3, 255):
            with self.subTest(scr=scr):
                mode["dsc_scr_version"] = scr
                self.assertFalse(_mode_validation(mode))

    def test_reject_slice_width_larger_than_picture(self):
        mode = self._valid_qualcomm_dsc_mode()
        for width in (0, 1441, 65536):
            with self.subTest(slice_width=width):
                mode["dsc_slice_width"] = width
                self.assertFalse(_mode_validation(mode))

    def test_exact_qualcomm_dsc_11_rgb_rate_control_combinations(self):
        mode = self._valid_qualcomm_dsc_mode()
        mode["dsc_version"] = 0x11
        for bpc, bpp in ((8, 8), (10, 8), (10, 10)):
            with self.subTest(bpc=bpc, bpp=bpp):
                mode["dsc_bits_per_component"] = bpc
                mode["dsc_bits_per_pixel"] = bpp
                self.assertTrue(_mode_validation(mode))
        for bpc, bpp in ((8, 7), (10, 7), (8, 10), (10, 6)):
            with self.subTest(unsupported=(bpc, bpp)):
                mode["dsc_bits_per_component"] = bpc
                mode["dsc_bits_per_pixel"] = bpp
                self.assertFalse(_mode_validation(mode))

    def test_exact_qualcomm_dsc_12_422_rate_control_combinations(self):
        mode = self._valid_qualcomm_dsc_mode()
        mode["dsc_chroma_format"] = 1  # MSM_CHROMA_422 in drm msm_drv.h
        for bpc, bpp in ((8, 7), (8, 8), (10, 7), (10, 8), (10, 10)):
            with self.subTest(valid=(bpc, bpp)):
                mode["dsc_bits_per_component"] = bpc
                mode["dsc_bits_per_pixel"] = bpp
                self.assertTrue(_mode_validation(mode))
        mode["dsc_bits_per_pixel"] = 6
        self.assertFalse(_mode_validation(mode))
        mode["dsc_version"] = 0x11
        mode["dsc_bits_per_pixel"] = 8
        self.assertFalse(_mode_validation(mode))

    def test_exact_qualcomm_dsc_12_420_rate_control_combinations(self):
        mode = self._valid_qualcomm_dsc_mode()
        mode["dsc_chroma_format"] = 2  # MSM_CHROMA_420 in drm msm_drv.h
        mode["dsc_bits_per_pixel"] = 6
        for bpc in (8, 10):
            with self.subTest(bpc=bpc):
                mode["dsc_bits_per_component"] = bpc
                self.assertTrue(_mode_validation(mode))
        for bpp in (7, 8, 10):
            with self.subTest(unsupported_bpp=bpp):
                mode["dsc_bits_per_pixel"] = bpp
                self.assertFalse(_mode_validation(mode))

    def test_reject_unsupported_chroma_and_subsampled_slice_geometry(self):
        mode = self._valid_qualcomm_dsc_mode()
        for invalid in (3, 255, -1):
            with self.subTest(chroma=invalid):
                mode["dsc_chroma_format"] = invalid
                self.assertFalse(_mode_validation(mode))
        mode["dsc_chroma_format"] = 2
        mode["dsc_bits_per_pixel"] = 6
        for sw in (1, 3, 5):
            with self.subTest(slice_width=sw):
                mode["dsc_slice_width"] = sw
                self.assertFalse(_mode_validation(mode))

    def test_stock_fdt_chroma_is_reported_not_assumed(self):
        source = sample_panel_fdt(chroma_format=1)
        report = panel_evidence_from_fdt(source)
        mode = report["panel_candidates"][0]["modes"][0]
        self.assertEqual(mode["dsc_chroma_format"], 1)
        self.assertFalse(mode["basic_geometry_and_dsc_valid"])
        self.assertFalse(report["production_panel_dts_approved"])
        default = panel_evidence_from_fdt(sample_panel_fdt())
        self.assertNotIn("dsc_chroma_format",
                         default["panel_candidates"][0]["modes"][0])

    def test_invalid_zero_slice_is_rejected_without_division(self):
        output = panel_evidence_from_fdt(sample_panel_fdt(slice_width=0))
        self.assertFalse(output["panel_candidates"][0]["modes"][0][
            "basic_geometry_and_dsc_valid"])

    def test_invalid_nondivisible_slice_is_rejected(self):
        output = panel_evidence_from_fdt(sample_panel_fdt(slice_width=499))
        self.assertFalse(output["panel_candidates"][0]["modes"][0][
            "basic_geometry_and_dsc_valid"])

    def test_empty_boolean_property_from_different_node_is_not_inherited(self):
        dt = FdtBuilder()
        dt.begin("")
        dt.begin("other")
        dt.prop("mi,local-hbm-enabled", b"")
        dt.end()
        dt.begin("panel@0")
        dt.string("qcom,mdss-dsi-panel-name", "my panel")
        dt.end()
        dt.end()
        result = panel_evidence_from_fdt(dt.build())
        self.assertFalse(result["panel_candidates"][0][
            "xiaomi_local_hbm_property_present"])

    def test_root_xiaomi_board_identity_is_reported_without_claiming_match(self):
        builder = FdtBuilder()
        builder.begin("")
        builder.prop("compatible", b"qcom,cape-mtp\x00qcom,cape\x00")
        builder.cells("qcom,msm-id", 530, 0x10000, 531, 0x10000)
        builder.cells("qcom,board-id", 0x10008, 0)
        builder.cells("xiaomi,miboard-id", 0xE, 0)
        builder.begin("other@0")
        builder.cells("xiaomi,miboard-id", 0xDEADBEEF)
        builder.end()
        builder.end()
        output = panel_evidence_from_fdt(builder.build())
        selectors = output["root_board_signals"]
        self.assertEqual(selectors["root_compatible"],
                         ["qcom,cape-mtp", "qcom,cape"])
        self.assertEqual(selectors["raw_root_id_cells"]["xiaomi,miboard-id"],
                         ["0x0000000e", "0x00000000"])
        self.assertEqual(selectors["raw_root_id_cells"]["qcom,msm-id"],
                         ["0x00000212", "0x00010000",
                          "0x00000213", "0x00010000"])
        self.assertFalse(selectors["stock_board_revision_verified"])
        self.assertEqual(output["panel_candidate_count"], 0)

    def test_non_u32_or_oversize_board_selector_is_not_misinterpreted(self):
        builder = FdtBuilder()
        builder.begin("")
        builder.prop("xiaomi,miboard-id", b"bad")
        builder.end()
        selectors = panel_evidence_from_fdt(
            builder.build())["root_board_signals"]
        self.assertNotIn("xiaomi,miboard-id", selectors["raw_root_id_cells"])
        self.assertFalse(selectors["stock_board_revision_verified"])

    def test_non_panel_fdt_does_not_claim_m11a(self):
        dt = FdtBuilder()
        dt.begin("")
        dt.begin("fingerprint")
        dt.string("compatible", "goodix,fingerprint")
        dt.end()
        dt.end()
        result = panel_evidence_from_fdt(dt.build())
        self.assertEqual(result["panel_candidate_count"], 0)
        self.assertFalse(result["production_panel_dts_approved"])

    def test_accept_real_format_64_bit_memory_reservation_and_terminator(self):
        fdt = with_synthetic_memreserve(sample_panel_fdt(), (
            (0x100000000, 0x2000), (0x100004000, 0x1000), (0, 0)))
        self.assertEqual(panel_evidence_from_fdt(fdt)["panel_candidate_count"], 1)

    def test_reject_unterminated_memory_reservation_map(self):
        fdt = with_synthetic_memreserve(sample_panel_fdt(), (
            (0x100000000, 0x1000),))
        with self.assertRaisesRegex(ValueError, "unterminated.*reservation"):
            fdt_nodes(fdt)

    def test_reject_overlapping_memory_reservation_ranges(self):
        fdt = with_synthetic_memreserve(sample_panel_fdt(), (
            (0x1000, 0x2000), (0x2000, 0x1000), (0, 0)))
        with self.assertRaisesRegex(ValueError, "overlapping.*reservation"):
            fdt_nodes(fdt)

    def test_reject_memory_reservation_map_inside_structure(self):
        fdt = bytearray(sample_panel_fdt())
        struct.pack_into(">I", fdt, 16, struct.unpack_from(">I", fdt, 8)[0])
        with self.assertRaisesRegex(ValueError, "reservation map overlaps"):
            fdt_nodes(fdt)

    def test_reject_unaligned_memory_reservation_map(self):
        fdt = bytearray(sample_panel_fdt())
        struct.pack_into(">I", fdt, 16, 41)
        with self.assertRaisesRegex(ValueError, "outside aligned bounds"):
            fdt_nodes(fdt)

    def test_reject_zero_length_or_overflowing_memory_reservations(self):
        for item in ((0x1000, 0), (0xfffffffffffffff0, 0x100)):
            with self.subTest(item=item):
                fdt = with_synthetic_memreserve(sample_panel_fdt(), (
                    item, (0, 0)))
                with self.assertRaisesRegex(ValueError, "invalid.*reservation range"):
                    fdt_nodes(fdt)

    def test_reject_unrecognized_future_fdt_header_version(self):
        fdt = bytearray(sample_panel_fdt())
        struct.pack_into(">I", fdt, 20, 99)
        with self.assertRaisesRegex(ValueError, "unsupported FDT header"):
            fdt_nodes(fdt)

    def test_reject_wrong_fdt_root(self):
        dt = FdtBuilder()
        dt.begin("bad-root")
        dt.end()
        with self.assertRaisesRegex(ValueError, "root"):
            fdt_nodes(dt.build())

    def test_reject_corrupt_property_strings_offset(self):
        dt = FdtBuilder()
        dt.begin("")
        dt.cells("dummy", 7)
        dt.end()
        raw = bytearray(dt.build())
        # FDT v17: header 40 + reserve-map 16 + root begin/name 8
        struct.pack_into(">I", raw, 56 + 8 + 8, 0x7FFFFFFF)
        with self.assertRaisesRegex(ValueError, "extends beyond block"):
            fdt_nodes(raw)

    def test_reject_truncated_structure_block(self):
        raw = bytearray(sample_panel_fdt())
        struct.pack_into(">I", raw, 36, 0xFFFFFFF0)
        # The existing FDT header validator may reject this before the
        # new structure parser sees it. Both paths must fail closed.
        with self.assertRaisesRegex(
                ValueError, "overflows totalsize|outside aligned bounds"):
            fdt_nodes(raw)

    def test_reject_corrupt_fdt_property_padding(self):
        dt = FdtBuilder()
        dt.begin("")
        dt.prop("short", b"\x01")
        dt.end()
        raw = bytearray(dt.build())
        # Header 40, reserve 16, root begin/empty name = 8,
        # property token/length/nameoff = 12, then 1-byte value and padding.
        raw[56 + 8 + 12 + 1] = 0xA5
        with self.assertRaisesRegex(ValueError, "property padding"):
            fdt_nodes(raw)

    def test_reject_invalid_token(self):
        dt = FdtBuilder()
        dt.begin("")
        dt.end()
        raw = bytearray(dt.build())
        struct.pack_into(">I", raw, 56, 0x99)
        with self.assertRaisesRegex(ValueError, "invalid FDT token"):
            fdt_nodes(raw)


if __name__ == "__main__":
    unittest.main()

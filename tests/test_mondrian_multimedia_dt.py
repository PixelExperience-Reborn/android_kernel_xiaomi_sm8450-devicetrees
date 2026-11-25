"""Contract for the Qualcomm audio/video DT stage and the DT driver-coverage gate."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


coverage = load("verify_dt_driver_coverage")
LOCK = json.loads((ROOT / "qualcomm-multimedia-dt-source-lock.json").read_text())
ALLOW = json.loads((ROOT / "dt-driver-coverage-allowlist.json").read_text())["allow"]


class MultimediaSources(unittest.TestCase):
    def test_lock_pins_release_era_sources(self):
        audio, video = LOCK["audio"], LOCK["video"]
        self.assertEqual(audio["commit"], "50ccb9f0fb8c6a138a0946e81ae5beb700264fd1")
        self.assertEqual(audio["xiaomi_overlay"]["blob"], "324f5d0fc75203fa8c6c549c3566e6c2a6ca64e3")
        self.assertEqual(audio["xiaomi_overlay"]["replaces"], "waipio-audio-overlay.dtsi")
        self.assertEqual(video["commit"], "7c85d65ec51887baa2886c5a9df8223d0b0cb01b")
        self.assertEqual(video["blobs"]["waipio-vidc.dtsi"], "a575b071743ae522916a064c24a721d12f67b8e8")
        self.assertTrue(LOCK["mmrm"]["selected"])
        self.assertIn("five voltage corners", LOCK["mmrm"]["reason"])
        overlay = (ROOT / LOCK["mmrm"]["overlay"]).read_text()
        self.assertEqual(overlay.count("<MMRM_DOMAIN_"), LOCK["mmrm"]["client_entries"])
        self.assertIn('mm-rail-corners = "lowsvs", "svs", "svsl1", "nom", "turbo";', overlay)
        blob = subprocess.check_output(["git", "-C", str(ROOT), "hash-object", "--no-filters",
                                        LOCK["mmrm"]["overlay"]], text=True).strip()
        self.assertEqual(blob, LOCK["mmrm"]["overlay_blob"])
        for gitlink, commit in ((audio["gitlink"], audio["commit"]), (video["gitlink"], video["commit"])):
            tree = subprocess.check_output(["git", "-C", str(ROOT), "ls-tree", "HEAD", gitlink], text=True)
            self.assertEqual(tree.strip(), "160000 commit " + commit + "\t" + gitlink)

    def test_binding_shims_point_to_kernel_dt_bindings(self):
        expected = {
            "qcom,audio-ext-clk.h": "<dt-bindings/clock/qcom,audio-ext-clk.h>",
            "qcom,gpr.h": "<dt-bindings/sound/qcom,gpr.h>",
            "qcom,lpass-cdc-clk-rsc.h": "<dt-bindings/sound/qcom,lpass-cdc-clk-rsc.h>",
            "audio-codec-port-types.h": "<dt-bindings/sound/audio-codec-port-types.h>",
        }
        self.assertEqual({p.name for p in (ROOT / "include/bindings").iterdir()}, set(expected))
        for name, target in expected.items():
            text = (ROOT / "include/bindings" / name).read_text()
            includes = [l for l in text.splitlines() if l.startswith("#include")]
            self.assertEqual(includes, ["#include " + target])

    def test_audio_board_overlay_selects_mondrian(self):
        dts = (ROOT / "qcom/mondrian-audio-board-overlay.dts").read_text()
        self.assertIn('#include "cape-audio-mtp.dtsi"', dts)
        self.assertIn("qcom,board-id = <0x10008 0>;", dts)
        self.assertIn("qcom,msm-id = <530 0x10000>, <531 0x10000>, <540 0x10000>;", dts)
        self.assertIn("xiaomi,miboard-id = <0xE 0>;", dts)

    def test_build_order_and_checks(self):
        tool = (ROOT / "tools/build_mondrian_multimedia.py").read_text()
        self.assertIn('run(["fdtoverlay", "-i", base, "-o", merged, soc_audio, soc_video, board_audio, board_mmrm])', tool)
        self.assertIn('"qcom,cdc-micbias1-mv = <0xabe>;"', tool)
        self.assertIn('{"qcom,msm-vidc-waipio", "qcom,msm-vidc-iris2"}', tool)
        self.assertIn('("awinic,aw882xx_smartpa", 2)', tool)
        self.assertIn("root_identity(merged) != root_identity(base)", tool)
        self.assertLess(tool.index("verify_sources(lock)"), tool.index("shutil.copytree"))


class CoverageAllowlist(unittest.TestCase):
    MUST_HAVE_DRIVER = {
        "qcom,ipa", "qcom,msm_gsi", "qcom,rmnet-ipa3", "qcom,msm-vidc", "qcom,msm-cvp",
        "qcom,waipio-cvp", "qcom,waipio-asoc-snd", "qcom,spf-core-platform", "qcom,lpass-cdc",
        "qcom,wcd938x-codec", "awinic,aw882xx_smartpa", "goodix,gt9916S", "goodix,fingerprint",
        "qcom,msm-mmrm", "qcom,cnss-qca6490", "qcom,sde-kms", "qcom,dsi-display",
        "xiaomi,wl2866d", "qcom,kgsl-3d0", "qcom,sn-nci",
    }

    def test_every_entry_is_justified(self):
        self.assertGreater(len(ALLOW), 0)
        for name, entry in ALLOW.items():
            with self.subTest(compatible=name):
                self.assertGreater(len(entry["reason"]), 30)
                self.assertLessEqual(set(entry), {"reason", "requires_config"})
                if "requires_config" in entry:
                    self.assertRegex(entry["requires_config"], r"^CONFIG_[A-Z0-9_]+$")

    def test_driver_devices_are_never_allowlisted(self):
        self.assertFalse(self.MUST_HAVE_DRIVER & set(ALLOW))


class CoverageTool(unittest.TestCase):
    def test_kbuild_option_resolves_composite_objects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Makefile").write_text("obj-$(CONFIG_FOO) += foo.o\nfoo-y := foo_core.o foo-bar.o\n"
                                           "obj-$(CONFIG_BAR) += bar.o\n")
            for name in ("foo_core.c", "foo-bar.c", "bar.c", "baz.c"):
                (root / name).write_text("")
            cache = {}
            self.assertEqual(coverage.kbuild_option(str(root / "foo_core.c"), cache), "CONFIG_FOO")
            self.assertEqual(coverage.kbuild_option(str(root / "foo-bar.c"), cache), "CONFIG_FOO")
            self.assertEqual(coverage.kbuild_option(str(root / "bar.c"), cache), "CONFIG_BAR")
            self.assertIsNone(coverage.kbuild_option(str(root / "baz.c"), cache))

    def test_scan_resolves_macro_compatibles(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "drv.c"
            src.write_text('#define NAME "vendor,dev"\n'
                           'static const struct of_device_id m[] = {{.compatible = NAME},\n'
                           '{.compatible = "vendor,plain"}, {}};\n'
                           'IRQCHIP_DECLARE(x, "vendor,irq", init);\n'
                           'np = of_find_compatible_node(NULL, NULL, "vendor,child");\n')
            drivers, quoted = coverage.scan(Path(tmp), wanted=frozenset({"vendor,child"}))
            self.assertEqual(set(drivers), {"vendor,dev", "vendor,plain", "vendor,irq"})
            self.assertEqual(set(quoted), {"vendor,child"})

    @unittest.skipUnless(shutil.which("dtc"), "dtc not installed")
    def test_enabled_nodes_respects_disabled_parents(self):
        dts = ('/dts-v1/; / { compatible = "v,root"; a { compatible = "v,a", "v,a2"; };'
               ' b { compatible = "v,b"; status = "disabled"; c { compatible = "v,c"; }; }; };')
        with tempfile.TemporaryDirectory() as tmp:
            dtb = Path(tmp) / "t.dtb"
            subprocess.run(["dtc", "-q", "-I", "dts", "-O", "dtb", "-o", str(dtb), "-"],
                           input=dts, text=True, check=True)
            nodes = dict((path, compats) for path, compats in coverage.enabled_nodes(dtb))
        self.assertEqual(nodes, {"/": ["v,root"], "/a": ["v,a", "v,a2"]})


if __name__ == "__main__":
    unittest.main()

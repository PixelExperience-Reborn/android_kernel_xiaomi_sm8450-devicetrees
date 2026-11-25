#!/usr/bin/env python3
"""Add the Qualcomm WAIPIO audio, video and MMRM device trees to the mondrian DTBs.

Inputs are the three M11A display DTBs from build_mondrian_m11a.py. The
Qualcomm audio-devicetree and video-devicetree gitlinks and the Xiaomi
waipio-audio-overlay.dtsi are verified against
qualcomm-multimedia-dt-source-lock.json. Xiaomi's overlay replaces
Qualcomm's only inside a temporary copy; the pinned sources stay pristine.

fdtoverlay applies only fragments, never an overlay's root properties, so the
merged DTB must keep its base root unchanged, while the mondrian audio board
overlay itself must carry the CAPE msm-ids and board-id 0x10008 that the
bootloader matches. MMRM comes from qcom/mondrian-mmrm-overlay.dts, built from
the stock OS3 CAPE values (see the lock). This is a diagnostic build, not a
bootloader dtbo.img.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory

from build_oem_dtbo import BASES, ROOT, run, verify_kernel_revision

LOCK = ROOT / "qualcomm-multimedia-dt-source-lock.json"


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_sources(lock):
    for kind in ("audio", "video"):
        entry = lock[kind]
        path = ROOT / entry["gitlink"]
        if git(ROOT, "ls-tree", "HEAD", entry["gitlink"]) != (
                "160000 commit " + entry["commit"] + "\t" + entry["gitlink"]):
            raise ValueError(f"{kind}: gitlink drift")
        if git(path, "rev-parse", "HEAD") != entry["commit"]:
            raise ValueError(f"{kind}: checkout is not the pinned Qualcomm commit")
        if git(path, "status", "--porcelain", "--untracked-files=no"):
            raise ValueError(f"{kind}: Qualcomm checkout is not pristine")
        for name, blob in entry["blobs"].items():
            if git(path, "hash-object", "--no-filters", name) != blob:
                raise ValueError(f"{kind}: original blob drift {name}")
    overlay = lock["audio"]["xiaomi_overlay"]
    if git(ROOT, "hash-object", "--no-filters", overlay["path"]) != overlay["blob"]:
        raise ValueError("Xiaomi waipio-audio-overlay.dtsi drift")
    mmrm = lock["mmrm"]
    if not mmrm["selected"]:
        raise ValueError("the stock-derived CAPE MMRM DT must be selected")
    if git(ROOT, "hash-object", "--no-filters", mmrm["overlay"]) != mmrm["overlay_blob"]:
        raise ValueError("mondrian MMRM overlay drift")


def compile_overlay(source, dest, kernel, includes, temp):
    preprocessed = temp / (Path(source).stem + ".dts")
    args = ["cpp", "-nostdinc", "-undef", "-D__DTS__", "-x", "assembler-with-cpp",
            "-I", kernel / "include", "-I", ROOT / "include"]
    for include in includes:
        args += ["-I", include]
    with preprocessed.open("wb") as stream:
        run([*args, source], stdout=stream)
    run(["dtc", "-q", "-@", "-I", "dts", "-O", "dtb", "-o", dest, preprocessed])


def enabled_nodes(dtb):
    """Return (path, compatibles, body) for nodes that are not disabled."""
    text = subprocess.run(["dtc", "-q", "-I", "dtb", "-O", "dts", str(dtb)],
                          check=True, capture_output=True, text=True).stdout
    nodes, stack = [], []
    for line in text.splitlines():
        stripped = line.strip()
        match = re.match(r"^(?:[\w-]+:\s*)?([\w,@.+/-]+)\s*\{$", stripped)
        if match:
            enabled = stack[-1]["enabled"] if stack else True
            stack.append({"name": match.group(1), "enabled": enabled, "compat": [], "body": []})
            continue
        if stripped == "};" and stack:
            node = stack.pop()
            path = "/".join(n["name"] for n in stack + [node]).replace("//", "/")
            if node["enabled"]:
                nodes.append((path, node["compat"], "\n".join(node["body"])))
            continue
        if not stack:
            continue
        stack[-1]["body"].append(stripped)
        compat = re.match(r'^compatible\s*=\s*(.*);$', stripped)
        if compat:
            stack[-1]["compat"] = [x for s in re.findall(r'"([^"]*)"', compat.group(1))
                                   for x in s.split("\\0") if x]
        status = re.match(r'^status\s*=\s*"([^"]*)";$', stripped)
        if status and status.group(1) not in ("okay", "ok"):
            stack[-1]["enabled"] = False
    return nodes


def verify_full(dtb):
    nodes = enabled_nodes(dtb)

    def having(compatible):
        return [(path, body) for path, compats, body in nodes if compatible in compats]

    checks = {}
    for compatible, minimum in (("qcom,waipio-asoc-snd", 1), ("qcom,spf-core-platform", 1),
                                ("qcom,lpass-cdc", 1), ("qcom,wcd938x-codec", 1),
                                ("awinic,aw882xx_smartpa", 2), ("qcom,msm-vidc", 1),
                                ("qcom,msm-vidc,context-bank", 1), ("qcom,msm-mmrm", 1)):
        found = having(compatible)
        if len(found) < minimum:
            raise ValueError(f"{dtb.name}: expected {minimum} enabled {compatible}, found {len(found)}")
        checks[compatible] = sorted(path for path, _ in found)
    vidc = [compats for _, compats, _ in nodes if "qcom,msm-vidc" in compats]
    if not all({"qcom,msm-vidc-waipio", "qcom,msm-vidc-iris2"} <= set(c) for c in vidc):
        raise ValueError(f"{dtb.name}: video node lacks the WAIPIO/IRIS2 compatibles")
    codec = having("qcom,wcd938x-codec")[0][1]
    if "qcom,cdc-micbias1-mv = <0xabe>;" not in codec:
        raise ValueError(f"{dtb.name}: Xiaomi mondrian 2750 mV micbias overlay not applied")
    mmrm = having("qcom,msm-mmrm")[0][1]
    # dtc prints string lists joined by \\0 when decompiling a DTB.
    for needle in ('mm-rail-corners = "lowsvs\\0svs\\0svsl1\\0nom\\0turbo";',
                   "scaling-fact-leak = <0x9c0f 0xa4035 0xbf72c 0xd7ef4 0x108639>;"):
        if needle not in mmrm:
            raise ValueError(f"{dtb.name}: MMRM node differs from the stock CAPE values")
    return checks


def root_identity(dtb):
    def read(prop, fmt):
        return subprocess.check_output(["fdtget", "-t", fmt, str(dtb), "/", prop], text=True).split()
    return {"model": " ".join(read("model", "s")), "qcom,msm-id": read("qcom,msm-id", "x"),
            "qcom,board-id": read("qcom,board-id", "x")}


def verify_board_overlay(dtbo):
    """fdtoverlay ignores overlay root properties; the bootloader reads them."""
    identity = root_identity(dtbo)
    if (not identity["model"].startswith("Mondrian")
            or identity["qcom,board-id"] != ["10008", "0"]
            or identity["qcom,msm-id"] != ["212", "10000", "213", "10000", "21c", "10000"]):
        raise ValueError(f"{dtbo.name}: not the mondrian CAPE board selector: {identity}")
    return identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path, required=True)
    parser.add_argument("--m11a-build", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    lock = json.loads(LOCK.read_text())
    m11a = json.loads((args.m11a_build / "mondrian-m11a-build.json").read_text())
    panel = json.loads((ROOT / "oem-m11a-panel-source-lock.json").read_text())
    kernel_sha = verify_kernel_revision(args.kernel, panel["display_source"]["kernel_commit"])
    if m11a["kernel_commit"] != kernel_sha:
        raise ValueError("M11A display build and kernel revision differ")
    verify_sources(lock)
    args.out.mkdir(parents=True, exist_ok=True)
    report = {"kernel_commit": kernel_sha,
              "audio_devicetree_commit": lock["audio"]["commit"],
              "video_devicetree_commit": lock["video"]["commit"],
              "xiaomi_audio_overlay_blob": lock["audio"]["xiaomi_overlay"]["blob"],
              "mmrm_dt_selected": True, "boards": {},
              "hardware_verified": False, "production_dtbo_approved": False}
    with TemporaryDirectory(dir=args.out) as directory:
        temp = Path(directory)
        audio = temp / "audio"
        shutil.copytree(ROOT / lock["audio"]["gitlink"], audio,
                        ignore=shutil.ignore_patterns(".git"))
        shutil.copyfile(ROOT / lock["audio"]["xiaomi_overlay"]["path"],
                        audio / lock["audio"]["xiaomi_overlay"]["replaces"])
        video = ROOT / lock["video"]["gitlink"]
        soc_audio = temp / "cape-audio.dtbo"
        soc_video = temp / "waipio-vidc.dtbo"
        board_audio = temp / "mondrian-audio-board.dtbo"
        compile_overlay(audio / "cape-audio.dts", soc_audio, args.kernel, [audio], temp)
        compile_overlay(video / "waipio-vidc.dts", soc_video, args.kernel, [video], temp)
        compile_overlay(ROOT / "qcom/mondrian-audio-board-overlay.dts", board_audio,
                        args.kernel, [audio], temp)
        report["board_overlay_selector"] = verify_board_overlay(board_audio)
        board_mmrm = temp / "mondrian-mmrm.dtbo"
        compile_overlay(ROOT / lock["mmrm"]["overlay"], board_mmrm, args.kernel, [], temp)
        outputs = [soc_audio, soc_video, board_audio, board_mmrm]
        for name in BASES:
            base = args.m11a_build / (name + "-mondrian-m11a.dtb")
            merged = temp / (name + "-mondrian-full.dtb")
            run(["fdtoverlay", "-i", base, "-o", merged, soc_audio, soc_video, board_audio, board_mmrm])
            if root_identity(merged) != root_identity(base):
                raise ValueError(f"{name}: multimedia overlays changed the base root identity")
            report["boards"][name] = {"input_sha256": digest(base),
                                      "output_sha256": digest(merged),
                                      "checks": verify_full(merged)}
            outputs.append(merged)
        report["overlays_sha256"] = {p.name: digest(p) for p in outputs[:4]}
        for binary in outputs:
            binary.replace(args.out / binary.name)
    (args.out / "mondrian-multimedia-build.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Applied Qualcomm audio (Xiaomi overlay) and video DT on " + ", ".join(report["boards"]))


if __name__ == "__main__":
    main()

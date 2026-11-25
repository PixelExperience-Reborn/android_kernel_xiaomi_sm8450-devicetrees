#!/usr/bin/env python3
"""Every enabled device in the mondrian DT must have an enabled driver.

For each enabled node with a `compatible`, find a driver that declares one of
its compatibles (`.compatible = "..."` or `*_OF_DECLARE`) in the kernel tree
or in one of the external module sources. For an in-tree driver, the Kbuild
object must be enabled (=y/=m) in the generated kernel .config. Nodes whose
compatible is only consumed by a parent driver or by the bootloader/userspace
must be listed, with a reason, in dt-driver-coverage-allowlist.json.
Anything else fails the check.
"""
import argparse
import collections
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DRIVER = re.compile(r'\.compatible\s*=\s*"([^"]+)"|_DECLARE\(\s*\w+\s*,\s*"([^"]+)"')
MACRO_COMPAT = re.compile(r'\.compatible\s*=\s*([A-Z][A-Z0-9_]+)\s*[,}]')
DEFINE = re.compile(r'^\s*#\s*define\s+([A-Z][A-Z0-9_]+)\s+"([^"]+)"', re.M)
STRING = re.compile(r'"([A-Za-z0-9][\w.,+\-]*)"')


def enabled_nodes(dtb):
    text = subprocess.run(["dtc", "-q", "-I", "dtb", "-O", "dts", str(dtb)],
                          check=True, capture_output=True, text=True).stdout
    nodes, stack = [], []
    for line in text.splitlines():
        stripped = line.strip()
        match = re.match(r"^(?:[\w-]+:\s*)?([\w,@.+/-]+)\s*\{$", stripped)
        if match:
            enabled = stack[-1]["enabled"] if stack else True
            stack.append({"name": match.group(1), "enabled": enabled, "compat": []})
            continue
        if stripped == "};" and stack:
            node = stack.pop()
            path = "/".join(n["name"] for n in stack + [node]).replace("//", "/")
            if node["enabled"] and node["compat"]:
                nodes.append((path, node["compat"]))
            continue
        if not stack:
            continue
        compat = re.match(r"^compatible\s*=\s*(.*);$", stripped)
        if compat:
            stack[-1]["compat"] = [x for s in re.findall(r'"([^"]*)"', compat.group(1))
                                   for x in s.split("\\0") if x]
        status = re.match(r'^status\s*=\s*"([^"]*)";$', stripped)
        if status and status.group(1) not in ("okay", "ok"):
            stack[-1]["enabled"] = False
    return nodes


def scan(root, skip=(), wanted=frozenset()):
    """Driver compatibles, plus the files quoting any `wanted` string."""
    drivers, strings = collections.defaultdict(set), collections.defaultdict(set)
    defines, macro_users = {}, collections.defaultdict(set)
    for directory, _, files in os.walk(root):
        if "/.git" in directory or any(part in directory for part in skip):
            continue
        # Only the arm64 architecture is built for mondrian.
        relative = os.path.relpath(directory, root)
        if relative.startswith("arch" + os.sep) and not relative.startswith(os.path.join("arch", "arm64")):
            continue
        for name in files:
            if not name.endswith((".c", ".h")):
                continue
            path = os.path.join(directory, name)
            text = Path(path).read_text(errors="ignore")
            for first, second in DRIVER.findall(text):
                drivers[first or second].add(path)
            for macro in MACRO_COMPAT.findall(text):
                macro_users[macro].add(path)
            defines.update(DEFINE.findall(text))
            for quoted in STRING.findall(text):
                if quoted in wanted:
                    strings[quoted].add(path)
    # `.compatible = NAME` with `#define NAME "vendor,device"` (e.g. Goodix FOD, CDM).
    for macro, paths in macro_users.items():
        if macro in defines:
            drivers[defines[macro]].update(paths)
    return drivers, strings


def kbuild_option(path, cache):
    """CONFIG_* (or 'y') that builds the object compiled from a C file."""
    directory, target = os.path.dirname(path), os.path.basename(path)[:-2] + ".o"
    for _ in range(4):
        for makefile in ("Makefile", "Kbuild"):
            mk = os.path.join(directory, makefile)
            if not os.path.exists(mk):
                continue
            text = cache.setdefault(mk, Path(mk).read_text(errors="ignore").replace("\\\n", " "))
            obj = re.escape(target)
            hit = re.search(r"obj-\$\((CONFIG_\w+)\)\s*[+:]?=[^\n]*(?<![\w-])" + obj, text)
            if hit:
                return hit.group(1)
            if re.search(r"obj-y\s*[+:]?=[^\n]*(?<![\w-])" + obj, text):
                return "y"
            hit = re.search(r"^\S+?-\$\((CONFIG_\w+)\)\s*[+:]?=[^\n]*(?<![\w-])" + obj, text, re.M)
            if hit:
                return hit.group(1)
            composite = re.search(r"^(\S+?)-(?:y|objs)\s*[+:]?=[^\n]*(?<![\w-])" + obj, text, re.M)
            if composite:
                parent = re.escape(composite.group(1)) + r"\.o"
                hit = re.search(r"obj-\$\((CONFIG_\w+)\)\s*[+:]?=[^\n]*(?<![\w-])" + parent, text)
                if hit:
                    return hit.group(1)
                if re.search(r"obj-y\s*[+:]?=[^\n]*(?<![\w-])" + parent, text):
                    return "y"
        target = os.path.basename(directory) + "/"
        directory = os.path.dirname(directory)
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dtb", type=Path, action="append", required=True)
    parser.add_argument("--kernel", type=Path, required=True)
    parser.add_argument("--kernel-config", type=Path, required=True)
    parser.add_argument("--module-source", action="append", default=[],
                        help="NAME=PATH of an external module source tree")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    config = {}
    for line in args.kernel_config.read_text().splitlines():
        hit = re.match(r"^(CONFIG_\w+)=(.*)$", line)
        if hit:
            config[hit.group(1)] = hit.group(2)
    allow = json.loads((ROOT / "dt-driver-coverage-allowlist.json").read_text())["allow"]
    boards = {dtb: enabled_nodes(dtb) for dtb in args.dtb}
    wanted = frozenset(c for nodes in boards.values() for _, compats in nodes for c in compats)
    kernel_drivers, kernel_strings = scan(args.kernel, ("/techpack/display", "/tools/", "/Documentation"), wanted)
    external = {}
    for spec in args.module_source:
        name, _, path = spec.partition("=")
        external[name] = scan(Path(path), (), wanted)
    cache, report, failures = {}, {"boards": {}}, []
    for dtb, nodes in boards.items():
        result = collections.OrderedDict()
        for path, compats in nodes:
            key = compats[0]
            if key in result:
                continue
            status, detail = None, []
            for compat in compats:
                for source in sorted(kernel_drivers.get(compat, ())):
                    option = kbuild_option(source, cache)
                    value = "y" if option == "y" else config.get(option, "n") if option else "?"
                    detail.append({"compatible": compat, "file": os.path.relpath(source, args.kernel),
                                   "option": option, "value": value})
            owners = sorted(n for n, (drivers, _) in external.items()
                            if any(c in drivers for c in compats))
            if any(d["value"] in ("y", "m") for d in detail):
                status = "kernel"
            elif owners:
                # An external module serves it, even if an older in-tree driver is off.
                status, detail = "external:" + "+".join(owners), owners
            elif detail:
                status = "kernel-driver-disabled"
            if status in (None, "kernel-driver-disabled"):
                rule = next((allow[c] for c in compats if c in allow), None)
                if rule is not None:
                    needed = rule.get("requires_config")
                    if needed and config.get(needed) not in ("y", "m"):
                        failures.append(f"{dtb.name}: {key}: allowlisted but {needed} is not enabled")
                    status = "allowlisted"
                    detail = rule["reason"]
                elif status is None:
                    # A parent/consumer driver that looks the node up by compatible.
                    consumers = []
                    for compat in compats:
                        for source in sorted(kernel_strings.get(compat, ())):
                            option = kbuild_option(source, cache)
                            value = "y" if option == "y" else config.get(option, "n") if option else "?"
                            if value in ("y", "m"):
                                consumers.append({"compatible": compat, "option": option,
                                                  "file": os.path.relpath(source, args.kernel)})
                        for name, (_, quoted) in external.items():
                            if quoted.get(compat):
                                consumers.append({"compatible": compat, "module": name})
                    if consumers:
                        status, detail = "consumed-by-enabled-driver", consumers
                    else:
                        status = "NO-DRIVER"
            if status.startswith(("NO-DRIVER", "kernel-driver-disabled")):
                failures.append(f"{dtb.name}: {path}: {', '.join(compats)} -> {status}")
            result[key] = {"path": path, "compatibles": compats, "status": status, "detail": detail}
        counts = collections.Counter(v["status"].split(":")[0] for v in result.values())
        report["boards"][dtb.name] = {"summary": dict(counts), "nodes": result}
    report["failures"] = failures
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    for name, board in report["boards"].items():
        print(f"{name}: {board['summary']}")
    if failures:
        for line in failures:
            print("[FAIL]", line)
        raise SystemExit(f"{len(failures)} enabled DT device(s) without an enabled driver")
    print("[PASS] every enabled mondrian DT device has an enabled kernel or external driver")


if __name__ == "__main__":
    main()

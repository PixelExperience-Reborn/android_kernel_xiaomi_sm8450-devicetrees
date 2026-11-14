#!/usr/bin/env python3
"""Independent read-only panel/DSC facts from a supplied Xiaomi stock FDT.

The source of truth is the original user-supplied stock DTB, not LineageOS.
This parses selected structural FDT properties only. It deliberately does NOT
export binary DCS command sequences, synthesize panel DTS or certify hardware.
Spec: https://devicetree-specification.readthedocs.io/en/stable/flattened-format.html
"""
import hashlib
import struct

from audit_xiaomi_stock_dtbo import FDT_MAGIC, parse_fdt

FDT_BEGIN_NODE = 1
FDT_END_NODE = 2
FDT_PROP = 3
FDT_NOP = 4
FDT_END = 9
MAX_NODES = 50000
MAX_PROPS = 250000
MAX_STRING = 256

MODE_U32_KEYS = {
    "qcom,mdss-dsi-panel-framerate": "refresh_hz",
    "qcom,mdss-dsi-panel-width": "width_px",
    "qcom,mdss-dsi-panel-height": "height_px",
    "qcom,mdss-dsc-version": "dsc_version",
    "qcom,mdss-dsc-scr-version": "dsc_scr_version",
    "qcom,mdss-dsc-slice-width": "dsc_slice_width",
    "qcom,mdss-dsc-slice-height": "dsc_slice_height",
    "qcom,mdss-dsc-slice-per-pkt": "dsc_slices_per_packet",
    "qcom,mdss-dsc-bit-per-component": "dsc_bits_per_component",
    "qcom,mdss-dsc-bit-per-pixel": "dsc_bits_per_pixel",
}
PANEL_U32_KEYS = {"qcom,mdss-dsi-bl-max-level": "backlight_max_level",
                  "qcom,mdss-dsi-bl-min-level": "backlight_min_level"}


def _be32(data, pos):
    if pos < 0 or pos + 4 > len(data):
        raise ValueError("truncated FDT u32")
    return struct.unpack_from(">I", data, pos)[0]


def _terminated_string(data, start, end, label):
    if start < 0 or start >= end:
        raise ValueError(f"{label} string offset outside FDT block")
    end_of_name = data.find(b"\x00", start, min(end, start + MAX_STRING))
    if end_of_name < 0:
        raise ValueError(f"unterminated {label} string")
    return data[start:end_of_name].decode("utf-8", "replace"), end_of_name + 1


def _u32_prop(props, name):
    data = props.get(name)
    return _be32(data, 0) if data is not None and len(data) == 4 else None


def _str_prop(props, name):
    data = props.get(name)
    if data is None or not data or len(data) > MAX_STRING or not data.endswith(b"\x00"):
        return None
    value = data.split(b"\x00", 1)[0].decode("utf-8", "replace")
    return value if value.isprintable() else None


def fdt_nodes(fdt):
    """Parse a valid FDT v17 token stream as {absolute_path: {property: bytes}}.

    A flat binary parser prevents picking arbitrary similar-named properties
    from another panel, device, or command blob. Every offset and token has
    an explicit bounded check; a malformed manufacturer input fails closed.
    """
    blob = bytes(parse_fdt(fdt))
    (magic, size, offset_struct, offset_strings, offset_reserve, version,
     last_comp, _boot_cpuid, strings_len, struct_len) = struct.unpack_from(
         ">10I", blob, 0)
    if magic != FDT_MAGIC or size != len(blob) or version < 17 or last_comp > 17:
        raise ValueError("unsupported FDT header or version")
    if (offset_struct % 4 or offset_reserve % 8 or
            offset_struct < 40 or offset_reserve < 40 or
            offset_struct + struct_len > size or
            offset_strings + strings_len > size):
        raise ValueError("FDT block offset/size outside aligned bounds")
    struct_end = offset_struct + struct_len
    strings_end = offset_strings + strings_len
    nodes = {}
    stack = []
    pos = offset_struct
    props_count = 0
    ended = False
    while pos < struct_end:
        tag = _be32(blob, pos)
        pos += 4
        if tag == FDT_BEGIN_NODE:
            name, pos = _terminated_string(blob, pos, struct_end, "node")
            pos = (pos + 3) & ~3
            if pos > struct_end or not stack and name:
                raise ValueError("invalid FDT root or node alignment")
            stack.append(name)
            node_path = "/" + "/".join(x for x in stack if x)
            if node_path in nodes or len(nodes) >= MAX_NODES:
                raise ValueError("duplicate or excessive FDT nodes")
            nodes[node_path] = {}
        elif tag == FDT_END_NODE:
            if not stack:
                raise ValueError("FDT_END_NODE without FDT_BEGIN_NODE")
            stack.pop()
        elif tag == FDT_PROP:
            if not stack or pos + 8 > struct_end:
                raise ValueError("FDT_PROP outside a node")
            length, name_off = struct.unpack_from(">2I", blob, pos)
            pos += 8
            if (name_off >= strings_len or length > struct_end - pos or
                    pos + ((length + 3) & ~3) > struct_end):
                raise ValueError("FDT_PROP name or data extends beyond block")
            name, _ = _terminated_string(
                blob, offset_strings + name_off, strings_end, "property")
            node_path = "/" + "/".join(x for x in stack if x)
            if name in nodes[node_path] or props_count >= MAX_PROPS:
                raise ValueError("duplicate or excessive FDT properties")
            nodes[node_path][name] = blob[pos:pos + length]
            props_count += 1
            pos += (length + 3) & ~3
        elif tag == FDT_NOP:
            continue
        elif tag == FDT_END:
            if stack or "/" not in nodes:
                raise ValueError("unclosed FDT nodes at FDT_END")
            if any(blob[pos:struct_end]):
                raise ValueError("nonzero bytes after FDT_END")
            ended = True
            break
        else:
            raise ValueError(f"invalid FDT token {tag}")
    if not ended:
        raise ValueError("FDT_END token missing")
    return nodes


def _mode_validation(mode):
    width = mode.get("width_px")
    height = mode.get("height_px")
    refresh = mode.get("refresh_hz")
    if not (isinstance(width, int) and 0 < width <= 16384 and
            isinstance(height, int) and 0 < height <= 16384 and
            isinstance(refresh, int) and 0 < refresh <= 300):
        return False
    if mode.get("compression_mode") != "dsc":
        return True
    sw = mode.get("dsc_slice_width")
    sh = mode.get("dsc_slice_height")
    count = mode.get("dsc_slices_per_packet")
    bpc = mode.get("dsc_bits_per_component")
    bpp = mode.get("dsc_bits_per_pixel")
    return bool(isinstance(sw, int) and sw > 0 and width % sw == 0 and
                isinstance(sh, int) and sh > 0 and
                isinstance(count, int) and 1 <= count <= 2 and
                isinstance(bpc, int) and 1 <= bpc <= 16 and
                isinstance(bpp, int) and 1 <= bpp <= 24)


def panel_evidence_from_fdt(fdt):
    nodes = fdt_nodes(fdt)
    panels = []
    for node_path, props in nodes.items():
        panel_name = _str_prop(props, "qcom,mdss-dsi-panel-name")
        if panel_name is None:
            continue
        panel = {
            "dt_node_path": node_path,
            "panel_name": panel_name,
            "panel_type": _str_prop(props, "qcom,mdss-dsi-panel-type"),
            "manufacturer_panel_source_verified": False,
            "device_panel_revision_verified": False,
        }
        for key, label in PANEL_U32_KEYS.items():
            value = _u32_prop(props, key)
            if value is not None:
                panel[label] = value
        ids = props.get("mi,panel-id")
        if ids is not None and len(ids) == 8:
            panel["xiaomi_panel_id_hex"] = [f"{c:08x}" for c in struct.unpack(">2I", ids)]
        modes = []
        descendant_props = [cp for path, cp in nodes.items()
                            if path == node_path or path.startswith(node_path + "/")]
        panel["xiaomi_local_hbm_property_present"] = any(
            "mi,local-hbm-enabled" in cp for cp in descendant_props)
        panel["panel_command_sequences_present"] = any(
            "qcom,mdss-dsi-on-command" in cp for cp in descendant_props)
        for mode_path, mp in nodes.items():
            if not mode_path.startswith(node_path + "/"):
                continue
            if "qcom,mdss-dsi-panel-framerate" not in mp:
                continue
            mode = {"dt_node_path": mode_path}
            for key, label in MODE_U32_KEYS.items():
                number = _u32_prop(mp, key)
                if number is not None:
                    mode[label] = number
            mode["compression_mode"] = _str_prop(mp, "qcom,compression-mode")
            mode["basic_geometry_and_dsc_valid"] = _mode_validation(mode)
            mode["physical_panel_validated"] = False
            modes.append(mode)
        panel["modes"] = modes
        panels.append(panel)
    return {
        "stock_fdt_sha256": hashlib.sha256(fdt).hexdigest(),
        "panel_candidates": panels,
        "panel_candidate_count": len(panels),
        "device_panel_revision_verified": False,
        "production_panel_dts_approved": False,
    }

#!/usr/bin/env python3
"""Read-only camera flash wiring evidence from an ORIGINAL Xiaomi stock FDT.

No source substitutions, LED mask guesses, foreign ROM DTS, DTBO generation,
flash GPIO writes, driver modifications or hardware qualification occur here.

Reuses the bounded structural FDT v17 parser from OEM panel auditing. Overlay
__fixups__ targets are unresolved external references until the exact OEM
base DTB has been qualified and the overlays applied.
"""
import struct

from audit_xiaomi_panel_evidence import fdt_nodes

MAX_FLASH_NODES = 32
MAX_REFERENCES = 8
MAX_MASK_NODES = 32
MAX_COMPATIBLE_BYTES = 1024
MAX_FIXUP_BYTES = 4096
MAX_FIXUPS = 256
PHANDLE_SENTINELS = frozenset((0, 0xFFFFFFFF, 0xDEADBEEF))
SOURCES = ("flash-source", "torch-source", "switch-source")


def _string_list(blob, *, limit):
    if not isinstance(blob, bytes) or not 0 < len(blob) <= limit:
        return []
    if not blob.endswith(b"\0"):
        return []
    parts = blob[:-1].split(b"\0")
    if len(parts) > MAX_FIXUPS or not all(parts):
        return []
    try:
        values = [part.decode("utf-8", "strict") for part in parts]
    except UnicodeDecodeError:
        return []
    if not all(x.isprintable() and len(x) <= 256 for x in values):
        return []
    return values


def _cells(blob, *, required=False):
    if blob is None:
        return [] if not required else None
    if not blob or len(blob) % 4 or len(blob) > 4 * MAX_REFERENCES:
        raise ValueError("invalid Camera FDT 32-bit cell array")
    return list(struct.unpack(">" + "I" * (len(blob) // 4), blob))


def _single_cell(props, key):
    data = props.get(key)
    if data is None:
        return None
    if len(data) != 4:
        raise ValueError(f"invalid {key} FDT u32")
    return struct.unpack(">I", data)[0]


def _lookup_phandles(nodes):
    lookup = {}
    for path, props in nodes.items():
        first = _single_cell(props, "phandle")
        second = _single_cell(props, "linux,phandle")
        if first is not None and second is not None and first != second:
            raise ValueError(f"conflicting phandle values at {path}")
        value = first if first is not None else second
        if value is None:
            continue
        if value in PHANDLE_SENTINELS or value in lookup:
            raise ValueError(f"duplicate or invalid phandle at {path}")
        lookup[value] = path
    return lookup


def _external_fixups(nodes):
    """Retain only symbol names and exact target locations from stock FDT."""
    raw = nodes.get("/__fixups__", {})
    if len(raw) > MAX_FIXUPS:
        raise ValueError("excessive external FDT fixup symbols")
    references = {}
    for symbol, content in raw.items():
        if not symbol.isidentifier() or len(symbol) > 128:
            continue
        for entry in _string_list(content, limit=MAX_FIXUP_BYTES):
            # The format is: /absolute/node/path:property:byte_offset
            try:
                node, prop, offset = entry.rsplit(":", 2)
                byte_offset = int(offset, 10)
            except ValueError:
                continue
            if (node not in nodes or not prop or not node.startswith("/")
                    or byte_offset < 0 or byte_offset % 4):
                continue
            blob = nodes[node].get(prop)
            if blob is None or byte_offset + 4 > len(blob):
                continue
            references.setdefault((node, prop, byte_offset), set()).add(symbol)
    return references


def camera_flash_evidence_from_fdt(fdt):
    nodes = fdt_nodes(fdt)
    phandles = _lookup_phandles(nodes)
    fixups = _external_fixups(nodes)
    flash_nodes = []
    masks = []
    unresolved_total = 0
    for path, props in nodes.items():
        compatible = _string_list(props.get("compatible"),
                                  limit=MAX_COMPATIBLE_BYTES)
        if "qcom,camera-flash" in compatible:
            if len(flash_nodes) >= MAX_FLASH_NODES:
                raise ValueError("excessive camera flash nodes in stock DTB")
            status = _string_list(props.get("status"), limit=128)
            candidate = {
                "node_path": path,
                "compatible": compatible,
                "cell_index": _single_cell(props, "cell-index"),
                "declared_status": status[0] if len(status) == 1 else None,
                "source_references": {},
                "all_sources_resolved_within_this_fdt": True,
                "physical_flash_hardware_qualified": False,
            }
            for property_name in SOURCES:
                blob = props.get(property_name)
                if blob is None:
                    candidate["source_references"][property_name] = []
                    continue
                cells = _cells(blob)
                refs = []
                for i, cell in enumerate(cells):
                    symbols = sorted(fixups.get((path, property_name, i * 4),
                                                set()))
                    if symbols:
                        status = "external_fixup_unresolved"
                        target = None
                    elif cell in phandles:
                        status = "local_phandle"
                        target = phandles[cell]
                    else:
                        status = "unresolved_phandle"
                        target = None
                    if status != "local_phandle":
                        unresolved_total += 1
                        candidate["all_sources_resolved_within_this_fdt"] = False
                    refs.append({
                        "cell_hex": f"0x{cell:08x}",
                        "resolution": status,
                        "local_target_node": target,
                        "external_fixup_symbols": symbols,
                    })
                candidate["source_references"][property_name] = refs
            flash_nodes.append(candidate)
        # Record all explicit switch masks from this particular stock FDT,
        # without assuming those masks belong to a mondrian flash circuit.
        if "qcom,led-mask" in props:
            if len(masks) >= MAX_MASK_NODES:
                raise ValueError("excessive LED mask nodes")
            masks.append({
                "node_path": path,
                "mask_as_published": _single_cell(props, "qcom,led-mask"),
                "mask_is_mondrian_camera_channel_verified": False,
            })

    return {
        "camera_flash_node_count": len(flash_nodes),
        "camera_flash_candidates": flash_nodes,
        "led_mask_candidates": masks,
        "unresolved_source_reference_count": unresolved_total,
        "pm8350c_flash_channel_or_gpio356_inferred": False,
        "oem_overlay_target_board_revision_confirmed": False,
        "stock_firmware_manufacturer_authenticity_verified": False,
        "camera_sensor_topology_verified": False,
        "camera_dtbo_safe_for_product": False,
        "physical_flash_hardware_qualified": False,
        "status": "READ_ONLY_OEM_CAMERA_FLASH_EVIDENCE_NOT_PRODUCT_READY",
    }

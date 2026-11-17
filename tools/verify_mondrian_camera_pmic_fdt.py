#!/usr/bin/env python3
"""Validate compiled Xiaomi OEM PM8350C triggers for the Qualcomm Camera driver.

This tests actual Cape+mondrian FDT source connectivity, NOT Camera sensors,
a physical PMIC LED channel, Camera HAL, or product readiness.
"""
import struct
from audit_xiaomi_panel_evidence import fdt_nodes

EXPECTED = {
    "pm8350c_flash0": ("qcom,flash_0", "flash0_trigger", None),
    "pm8350c_torch0": ("qcom,torch_0", "torch0_trigger", None),
    "pm8350c_switch0": ("qcom,led_switch_0", "switch0_trigger", 9),
    "pm8350c_switch1": ("qcom,led_switch_1", "switch1_trigger", 6),
    "pm8350c_switch2": ("qcom,led_switch_2", "switch2_trigger", 15),
}
DONOR_CAMERA_COMPATIBLES = {b"qcom,camera-flash", b"qcom,cam-i2c-flash"}


def _string(props, name):
    raw = props.get(name)
    if (not raw or len(raw) > 4096 or not raw.endswith(b"\0")
            or b"\0" in raw[:-1]):
        raise ValueError("missing/invalid FDT string: " + name)
    try:
        decoded = raw[:-1].decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError("invalid FDT ASCII: " + name) from error
    if not decoded or not decoded.isprintable():
        raise ValueError("invalid FDT text property: " + name)
    return decoded


def _compat(props):
    raw = props.get("compatible", b"")
    if not raw or len(raw) > 2048 or not raw.endswith(b"\0"):
        return set()
    return {entry for entry in raw[:-1].split(b"\0") if entry}


def _u32(props, name):
    raw = props.get(name)
    if raw is None or len(raw) != 4:
        raise ValueError("missing/non-u32 FDT property: " + name)
    return struct.unpack(">I", raw)[0]


def verify_mondrian_camera_pmic_fdt(blob):
    nodes = fdt_nodes(blob)
    roots = [
        path for path, props in nodes.items()
        if b"qcom,pm8350c-flash-led" in _compat(props)
    ]
    if len(roots) != 1:
        raise ValueError("expected exactly one OEM PM8350C Flash controller")
    root = roots[0]
    if _string(nodes[root], "status") not in ("ok", "okay"):
        raise ValueError("OEM PM8350C Flash controller is not enabled")
    symbols = nodes.get("/__symbols__", {})
    targets = {}
    led_masks = {}
    for label, (child, trigger, mask) in EXPECTED.items():
        target = root + "/" + child
        if target not in nodes:
            raise ValueError("missing Xiaomi PM8350C child " + label)
        if _string(symbols, label) != target:
            raise ValueError("unresolved or mismatched PMIC phandle " + label)
        props = nodes[target]
        if _string(props, "qcom,default-led-trigger") != trigger:
            raise ValueError("Qualcomm Camera flash trigger mismatch " + label)
        if mask is not None:
            selected_mask = _u32(props, "qcom,led-mask")
            if selected_mask != mask or "qcom,symmetry-en" not in props:
                raise ValueError("unreviewed OEM common LED-mask change " + label)
            led_masks[label] = selected_mask
        targets[label] = target
    # Only the OEM PMIC resources are verified. No unqualified Camera
    # consumer may be enabled by this source-only mondrian board build.
    for path, props in nodes.items():
        if _compat(props) & DONOR_CAMERA_COMPATIBLES:
            if props.get("status") not in (b"disabled\x00", b"reserved\x00"):
                raise ValueError("unqualified active Camera flash consumer " + path)
    return {
        "oem_pmic_source_links_resolved_in_compiled_dtb": True,
        "flash_torch_and_switch_phandle_targets": targets,
        "xiaomi_common_switch_masks_as_published": led_masks,
        "mondrian_physical_flash_channel_mapping_verified": False,
        "camera_consumer_with_sensors_enabled": False,
        "camera_sensor_power_cci_eeprom_verified": False,
        "camera_hal_and_hardware_verified": False,
        "production_camera_flash_approved": False,
        "status": "OEM_PMIC_SOURCES_COMPILED_NOT_DEVICE_CAMERA_READY",
    }

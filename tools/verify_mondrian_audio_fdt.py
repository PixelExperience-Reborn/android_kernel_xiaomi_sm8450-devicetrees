#!/usr/bin/env python3
"""Read-only compiled-FDT guard for Xiaomi mondrian's native speaker hardware.

Only the Xiaomi-released SM8475 board is authoritative. This deliberately
does not select an Audio kernel driver, codec, firmware, Android HAL or a
production audio overlay. It checks actual OEM Cape+mondrian merged DTBs.
"""
import struct

from audit_xiaomi_panel_evidence import fdt_nodes


AMPLIFIERS = {
    0x34: {"channel": 0, "irq": 88, "reset": 1, "switch": 52},
    0x35: {"channel": 1, "irq": 63, "reset": 3, "switch": None},
}
MI2S2 = {
    "tert_tdm_din_active": ("mi2s2_data0", "gpio122"),
    "tert_tdm_dout_active": ("mi2s2_data1", "gpio124"),
    "tert_tdm_clk_active": ("mi2s2_sck", "gpio121"),
    "tert_tdm_ws_active": ("mi2s2_ws", "gpio123"),
}


def _string(props, name):
    raw = props.get(name)
    if not raw or len(raw) > 4096 or not raw.endswith(b"\0") or b"\0" in raw[:-1]:
        raise ValueError("missing/invalid OEM audio string: " + name)
    try:
        return raw[:-1].decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("non-ASCII OEM audio property: " + name) from exc


def _cells(props, name, count):
    raw = props.get(name)
    if raw is None or len(raw) != count * 4:
        raise ValueError("invalid OEM audio u32 cells: " + name)
    return struct.unpack(">" + "I" * count, raw)


def verify_nodes(nodes):
    symbols = nodes.get("/__symbols__", {})
    i2c = _string(symbols, "qupv3_se15_i2c")
    tlmm = _string(symbols, "tlmm")
    if i2c not in nodes or tlmm not in nodes:
        raise ValueError("OEM I2C15/TLMM symbol does not resolve in compiled DTB")
    tlmm_phandle = _cells(nodes[tlmm], "phandle", 1)[0]
    if not tlmm_phandle:
        raise ValueError("OEM TLMM phandle is zero")
    if _string(nodes[i2c], "status") not in ("ok", "okay"):
        raise ValueError("OEM speaker I2C15 is not enabled")

    matched = [
        p for p, props in nodes.items()
        if props.get("compatible") == b"awinic,aw882xx_smartpa\0"
    ]
    expected_paths = {i2c + "/aw882xx_smartpa@" + format(addr, "x")
                      for addr in AMPLIFIERS}
    if set(matched) != expected_paths:
        raise ValueError("expected exactly two Xiaomi AW882xx devices on I2C15")

    amp_info = {}
    for addr, expected in AMPLIFIERS.items():
        path = i2c + "/aw882xx_smartpa@" + format(addr, "x")
        props = nodes[path]
        if _string(props, "status") not in ("ok", "okay"):
            raise ValueError("OEM AW882xx amplifier disabled")
        if _cells(props, "reg", 1)[0] != addr:
            raise ValueError("OEM AW882xx I2C address differs from node address")
        if _cells(props, "sound-channel", 1)[0] != expected["channel"]:
            raise ValueError("OEM AW882xx channel mismatch")
        for prop, pin in (("irq-gpio", expected["irq"]),
                          ("reset-gpio", expected["reset"])):
            value = _cells(props, prop, 3)
            if value != (tlmm_phandle, pin, 0x2008 if prop == "irq-gpio" else 0):
                raise ValueError("OEM AW882xx GPIO or provider mismatch: " + prop)
        switch = expected["switch"]
        if switch is not None:
            if _cells(props, "spksw-gpio", 3) != (tlmm_phandle, switch, 0):
                raise ValueError("OEM top speaker switch GPIO mismatch")
        elif "spksw-gpio" in props:
            raise ValueError("unexpected bottom speaker switch GPIO")
        amp_info[hex(addr)] = {
            "i2c_address": hex(addr), "channel": expected["channel"],
            "irq_gpio": expected["irq"], "reset_gpio": expected["reset"],
            "speaker_switch_gpio": switch,
        }

    mi2s_pins = {}
    for label, (function, pin) in MI2S2.items():
        # Other Cape pinctrl states may legitimately share the same mux
        # function. Require the exact Xiaomi mondrian-labelled state,
        # not an incorrect global uniqueness assumption.
        path = _string(symbols, label)
        if not path.startswith(tlmm + "/") or path + "/mux" not in nodes:
            raise ValueError("unresolved OEM mondrian MI2S2 pinctrl " + label)
        props = nodes[path + "/mux"]
        if (props.get("function") != function.encode() + b"\0"
                or props.get("pins") != pin.encode() + b"\0"):
            raise ValueError("wrong OEM MI2S2 pin assignment " + label)
        mi2s_pins[function] = pin

    return {
        "status": "OEM_MONDRIAN_SPEAKER_BOARD_DTB_VERIFIED_NOT_AUDIO_READY",
        "oem_board_speaker_gpio_and_i2c_verified": True,
        "oem_two_aw882xx_i2c_bus": i2c,
        "oem_aw882xx_amplifiers": amp_info,
        "oem_mi2s2_pins": mi2s_pins,
        "audio_driver_abi_verified": False,
        "audio_codec_calibration_verified": False,
        "audio_hal_verified": False,
        "physical_audio_tested": False,
        "production_audio_approved": False,
    }


def verify_mondrian_audio_fdt(blob):
    return verify_nodes(fdt_nodes(blob))

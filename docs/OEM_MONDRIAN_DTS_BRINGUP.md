# mondrian OEM DTS baseline — AOSP 17

This directory stages only the **Xiaomi-released mondrian** DTS hardware subset, not any LineageOS source. Provenance: [MiCode/kernel_devicetree at `34e6cc7d832ed9c655b9d79bc3ffe1d625146b7c`](https://github.com/MiCode/kernel_devicetree/commit/34e6cc7d832ed9c655b9d79bc3ffe1d625146b7c), branch `mondrian-s-oss`.

The seven files are direct hardware descriptions and dependencies. All original Git blob SHA-1 IDs are recorded in [`oem-source-lock.json`](../oem-source-lock.json). Six files are unchanged. One **surgical adaptation**, in `qcom/mondrian-sm8475.dtsi`, replaces the SPI touch `compatible = "xiaomi,m11a-spi";` with `compatible = "goodix,gt9916S";` because the PE-Reborn OEM-derived kernel at `2466406` has the latter OF device ID in `goodix_brl_spi.c`. The source test reconstructs the exact Xiaomi blob from the adapted file, rejecting any additional alteration.

**Important:** Two additional, explicitly tracked adaptations add `.bin` to the Goodix firmware and configuration filenames. This is verified against the already available mondrian vendor source tree at commit `3ccf06a7`, which packages `goodix_firmware_m11a.bin` and `goodix_cfg_group_m11a.bin` to `/vendor/firmware/`. The Goodix pdev-id-0 path passes the DT string unchanged to `request_firmware()`. Binary firmware is not copied into the DTS tree; AOSP17 vendor packaging and runtime are still unqualified. The separate Xiaomi touch feature node, pinctrl, regulator voltages, panel and board ID are untouched. Do not infer proper runtime binding from source syntax alone.

## Missing build inputs

This baseline does **not** yet constitute complete DTB/DTBO. The Cape/Waipio platform include and PMIC closure are incomplete, as are the display and camera overlay descriptions and DTC build files. Build `cape.dtb`, `cape-v2.dtb`, `capep.dtb` and the mondrian overlays from the same OEM and Qualcomm BSP generation, then validate them with `fdtoverlay`. No stock-compatible `dtbo.img`, `vendor_boot.img` or tested image is claimed.

The base kernel, Kconfig and Qualcomm external modules must be pinned together. No foreign-device DTS or radio support is selected.

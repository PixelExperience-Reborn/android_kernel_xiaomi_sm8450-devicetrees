# mondrian OEM DTS baseline — AOSP 17

This directory stages only the **Xiaomi-released mondrian** DTS hardware subset, not any LineageOS source. Provenance: [MiCode/kernel_devicetree at `34e6cc7d832ed9c655b9d79bc3ffe1d625146b7c`](https://github.com/MiCode/kernel_devicetree/commit/34e6cc7d832ed9c655b9d79bc3ffe1d625146b7c), branch `mondrian-s-oss`.

Seven manufacturer hardware files are selected. Six blobs are unchanged, and three narrow, individually recorded edits to `qcom/mondrian-sm8475.dtsi` align Goodix's compatible string and the two firmware/config basenames with the existing OEM-derived kernel and vendor files. All original blob IDs are in `oem-source-lock.json`. CI reconstructs the original Xiaomi blob to verify no other changes occurred.

**Important:** Two additional, explicitly tracked adaptations add `.bin` to the Goodix firmware and configuration filenames. This is verified against the already available mondrian vendor source tree at commit `3ccf06a7`, which packages `goodix_firmware_m11a.bin` and `goodix_cfg_group_m11a.bin` to `/vendor/firmware/`. The Goodix pdev-id-0 path passes the DT string unchanged to `request_firmware()`. Binary firmware is not copied into the DTS tree; AOSP17 vendor packaging and runtime are still unqualified. The separate Xiaomi touch feature node, pinctrl, regulator voltages, panel and board ID are untouched. Do not infer proper runtime binding from source syntax alone.

## Confirmed diagnostic board build; missing shipping inputs

The pinned manufacturer Cape/Waipio platform includes and PMIC dependencies resolve in the current diagnostic build. The three Cape base DTBs and mondrian board DTBO compile and apply in [CI #43010141003](https://github.com/PixelExperience-Reborn/android_kernel_xiaomi_sm8450-devicetrees/actions/runs/43010141003). The compiled tree is also checked for the Goodix OF match and exact vendor firmware/config names.

**Still missing:** matching M11A display and camera/audio overlay compilation, complete bootloader-aware `dtbo.img` packaging, Qualcomm external modules and real mondrian hardware validation. A diagnostic Cape/board DTBO PASS is not a production `dtbo.img` or Android 17 boot PASS.

The base kernel, Kconfig and Qualcomm external modules must be pinned together. No foreign-device DTS or radio support is selected.

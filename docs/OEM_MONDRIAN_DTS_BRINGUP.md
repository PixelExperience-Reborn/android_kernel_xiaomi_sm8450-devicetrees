# mondrian OEM DTS baseline — AOSP 17

This directory stages only the **Xiaomi-released mondrian** DTS hardware subset, not any LineageOS source. Provenance: [MiCode/kernel_devicetree at `34e6cc7d832ed9c655b9d79bc3ffe1d625146b7c`](https://github.com/MiCode/kernel_devicetree/commit/34e6cc7d832ed9c655b9d79bc3ffe1d625146b7c), branch `mondrian-s-oss`.

Seven manufacturer hardware files are selected. Six blobs are unchanged, and three narrow, individually recorded edits to `qcom/mondrian-sm8475.dtsi` align Goodix's compatible string and the two firmware/config basenames with the existing OEM-derived kernel and vendor files. All original blob IDs are in `oem-source-lock.json`. CI reconstructs the original Xiaomi blob to verify no other changes occurred.

**Important:** Two additional, explicitly tracked adaptations add `.bin` to the Goodix firmware and configuration filenames. This is verified against the already available mondrian vendor source tree at commit `3ccf06a7`, which packages `goodix_firmware_m11a.bin` and `goodix_cfg_group_m11a.bin` to `/vendor/firmware/`. The Goodix pdev-id-0 path passes the DT string unchanged to `request_firmware()`. Binary firmware is not copied into the DTS tree; AOSP17 vendor packaging and runtime are still unqualified. The separate Xiaomi touch feature node, pinctrl, regulator voltages, panel and board ID are untouched. Do not infer proper runtime binding from source syntax alone.

## Confirmed diagnostic board build; missing shipping inputs

The pinned manufacturer Cape/Waipio platform includes and PMIC dependencies resolve in the current diagnostic build. The three Cape base DTBs and mondrian board DTBO compile and apply in [CI #43010141003](https://github.com/PixelExperience-Reborn/android_kernel_xiaomi_sm8450-devicetrees/actions/runs/43010141003). The compiled tree is also checked for the Goodix OF match and exact vendor firmware/config names.

**Still missing:** matching M11A display and camera/audio overlay compilation, complete bootloader-aware `dtbo.img` packaging, Qualcomm external modules and real mondrian hardware validation. A diagnostic Cape/board DTBO PASS is not a production `dtbo.img` or Android 17 boot PASS.

The base kernel, Kconfig and Qualcomm external modules must be pinned together. No foreign-device DTS or radio support is selected.


## 17 Nov 2026 — read-only manufacturer Camera DTBO/PM8350C evidence gate

The OEM Kernel/Qualcomm Camera diagnostic at
[modules CI #43974526537](https://github.com/PixelExperience-Reborn/android_kernel_xiaomi_sm8450-modules/actions/runs/43974526537)
has passed real compile and static ELF/ABI tests at module revision
5594d54c215d05cac5a7c5a78abf3d4db965450b. The unverified
\`yudi\` auxiliary Camera flash GPIO 356 is intentionally excluded
from the compiled \`mondrian\` Camera path; generic Qualcomm PMIC/I2C
remains enabled. This is NOT a test of the actual flash hardware.

To avoid copying LineageOS values or guessing whether the physical
\`mondrian\` LED switch uses channel mask 1 or mask 9, use the
**original Xiaomi stock Fastboot \`dtbo.img\`** from the owner's exact
SKU and region. Existing \`tools/audit_xiaomi_fastboot_package.py\`
verifies archive integrity and safely extracts the bounded DTBO only
for read-only analysis. Its JSON now includes
\`entries[].manufacturer_camera_flash_structure\`, parsed directly
from each FDT with structural bounds validation.

The new Camera report records each exact \`qcom,camera-flash\` node,
its \`flash-source\`, \`torch-source\`, \`switch-source\`, local phandle
links, externally unresolved \`__fixups__\` symbols, and published
\`qcom,led-mask\` values. Crucially, **external fixups are not treated
as resolved connections**, and a reported mask never automatically
authorizes its use as \`mondrian\` wiring. No sensor array, PMIC current
limit, GPIO, board ID or stock provenance is fabricated. The report
remains \`camera_dtbo_safe_for_product=false\` until matching original
Xiaomi firmware evidence, the actual overlay/base merge, bootloader
selection, regulators, sensors, and physical flash tests are complete.

Read-only procedure:

\`\`\`sh
python3 tools/audit_xiaomi_fastboot_package.py \
  --fastboot-tgz /path/to/official/mondrian_*_images_*.tgz \
  --expected-sha256 <original_fastboot_archive_sha256> \
  --out /tmp/pe-mondrian-oem-camera
\`\`\`

The recorded archive digest is an integrity check, **not** independent
proof of Xiaomi authenticity. No manufacturer Camera DTBO has been
supplied in this CI environment; synthetic FDT test fixtures are not
physical wiring evidence. This stage does not compile/ship a Camera
overlay, import LineageOS source, mutate DTB/DTBO images, touch
\`seventeen\`, or change the already-passed OEM Kernel/Modules builds.

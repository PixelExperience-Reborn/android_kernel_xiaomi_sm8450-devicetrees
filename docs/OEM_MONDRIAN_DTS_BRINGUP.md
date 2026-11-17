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


## 17 November 2026 — Camera Flash evidence in both OEM boot FDT sources

After the source-only and coherent DTBO tests passed on devicetrees
commit `421b4d49000dcf8c5db457555a7323b236b55ba0`:
- [DTBO contract](https://github.com/PixelExperience-Reborn/android_kernel_xiaomi_sm8450-devicetrees/actions/runs/43977761777) — SUCCESS.
- [Coherent Cape board compilation](https://github.com/PixelExperience-Reborn/android_kernel_xiaomi_sm8450-devicetrees/actions/runs/43977761772) — SUCCESS.

The original Xiaomi fastboot camera provenance audit is now applied to
**both** DTBO table entries and FDTs embedded in `vendor_boot.img` v3/v4.
The `stock_vendor_boot.embedded_dtbs[].manufacturer_camera_flash_structure`
JSON field uses exactly the same bounded Xiaomi FDT reader as
`entries[].manufacturer_camera_flash_structure` from `dtbo.img`.
This avoids missing a factory camera flash node that exists only in an
OEM vendor-boot DTB.

The report records only structurally present Camera flash nodes, local
phandle connections, unresolved external `__fixups__` and raw published
LED masks. A referenced PM8350C symbol or a mask value of 1/9 is
**candidate evidence, not verified mondrian hardware wiring**.
Synthetic test FDTs cover both vendor_boot header layouts, external
fixup handling, malformed LED masks and Fastboot aggregation. Neither
synthetic tests nor boot-image hashes establish manufacturer authenticity
or physical function.

No original Xiaomi mondrian stock fastboot archive has been supplied for
this stage. Until it is inspected and matched to the exact OEM firmware,
SKU, sensor firmware and actual bootloader configuration, the following
remain false: production Camera DTBO approval, GPIO356 approval, LED
channel mask verification, hardware Camera/torch/flash validation.
This is independent PE-Reborn AOSP 17 code; no LineageOS DTS is copied
and no `seventeen` branch, panel source, Android HAL or shipping image is
modified.


## 17 Nov 2026 — validate actual Qualcomm Camera PMIC sources in built OEM DTBs

The combined OEM Kernel, MMRM, Display, WLAN and Camera source build passed
[CI #43985719293](https://github.com/PixelExperience-Reborn/android_kernel_xiaomi_sm8450-modules/actions/runs/43985719293).

The PE-Reborn Device Tree builder now parses **compiled** Cape, Cape-v2,
and Capep DTBs after applying the actual mondrian board overlay.
It requires exactly one enabled Xiaomi/Qualcomm PM8350C flash controller,
and checks the compiled symbol targets for `pm8350c_flash0`,
`pm8350c_torch0` and `pm8350c_switch0/1/2`.
It confirms OEM trigger strings as required by Camera
`cam_flash_soc.c`, and records the Xiaomi common DTS baseline masks
9, 6, and 15 **without interpreting these values as actual mondrian
flash-channel mapping**. It refuses any prematurely enabled Camera
Flash or donor I2C Flash consumer.

This step validates source-to-compiled-FDT dependency consistency, not
Camera sensor selection, regulator/CCI power sequencing, physical LED
channels, Camera HAL, or product DTBO. No Lineage sources, yudi GPIO356,
other device targets, or production module load configuration are
included. The seven original Xiaomi board source blobs remain unmodified.


## 17 November 2026 — compiled FDT alignment recovery without weakening OEM checks

Diagnostic Cape/board DTBO builds on Devicetrees commit
`c6fab787f243eb048b15cb407691905d4993f1bf`
failed in [CI #44004211895](https://github.com/PixelExperience-Reborn/android_kernel_xiaomi_sm8450-devicetrees/actions/runs/44004211895)
and [CI #44004211815](https://github.com/PixelExperience-Reborn/android_kernel_xiaomi_sm8450-devicetrees/actions/runs/44004211815).
The OEM Cape DTBs and board overlay compiled, `fdtoverlay` applied,
and the **new** PMIC inspection stage reached
`fdt_nodes(): invalid FDT property padding`. This is a strict
structural inspection error, not evidence of a Camera kernel-ABI failure.

DTSpec section 5.4.1 requires zeroed property alignment bytes.
Do not delete this validation from the read-only original Xiaomi
stock DTBO/vendor_boot parser. Instead, after `fdtoverlay`, use
the already-required `fdtget` to confirm the original merged DTB
has the expected Cape board model, then reserialize an **ephemeral**
inspection copy using trusted `dtc -I dtb -O dtb`.
Before PMIC inspection, require that the complete original DTS and
reserialized DTS byte-for-byte agree under the same `dtc` version.
Any semantic change fails the CI. The strict original `fdt_nodes`
is then applied to that copy. Its SHA256 and the original merged DTB's
SHA256 are reported separately; the original DTB is neither replaced
nor promoted as production.

The unchanged Camera/PMIC gate still requires original OEM flash,
torch, switch trigger labels and the Xiaomi common LED masks
(9, 6, 15); these **do not qualify physical mondrian flash wiring**.
An unqualified Camera consumer, donor GPIO356, altered sensor wiring
or other device configuration remains blocked. A dedicated regression
test verifies original-byte preservation, complete DTS equality and
failure on any detected property change. This is an isolated diagnostic
tooling fix, not an AOSP17 product-image or hardware qualification.


## 17 November 2026 — source Xiaomi's genuine Cape Camera platform separately

The successful OEM DTBO checks at
[CI #44005240069](https://github.com/PixelExperience-Reborn/android_kernel_xiaomi_sm8450-devicetrees/actions/runs/44005240069)
cover the *base SoC* Cape DTB and our existing mondrian overlay;
they do not contain the separate Qualcomm Camera controller DTS.
Manufacturer `MiCode/kernel_devicetree` has no
`qcom/cape-camera.dtsi` and does not define the CCI0/CCI1 and
CSIPHY0..5 Camera controller hierarchy.

The separate **official Xiaomi** repository
[`MiCode/vendor_qcom_proprietary_camera-devicetree`](https://github.com/MiCode/vendor_qcom_proprietary_camera-devicetree)
contains that generic Cape controller source. The available
`flame-u-oss` source revision
`a59a63bd498b94074c41357a466874b99aec62a8` is
now pinned under the **Git submodule**
`upstream/xiaomi-camera-platform` in PE-Reborn. These common
Cape definitions provide `qcom,cci` CCI controllers, CSI PHY,
Camera Request Manager and CPAS bindings. The pinned MiCode
Camera driver `9ed4ce96d49c0759c6365627113c5f59c2407942`
declares OF matches for `qcom,cci` and `qcom,csiphy`.

**Source branch naming is not board qualification.** `flame-u-oss`
is a carrier for generic manufacturer Cape sources; `flame`,
Cape MTP/QRD/CDP and ukee sensor dtsi/dtbo are not authorized for
`mondrian`. Do not include `cape-camera-sensor-mtp.dtsi`,
copy camera reset GPIOs or select the PM8350C flash channel
according to another device. A fail-closed source audit validates
Gitlink, manufacturer commit and tree, the original blobs, both CCI
and six CSIPHY declarations, and prevents importing any reference
sensor include into the active board overlay.

This *first stage* installs a reproducible, pristine OEM
Camera **platform source**, not an active Camera DTBO. Next:
construct a **native mondrian-only** Camera platform overlay with
the pinned OEM Kernel/Cape platform and device camera wiring
verified separately. Keep source pinning, compilation, ABI,
sensor power/CCI, HAL and physical flash qualification distinct.
No production Camera image, vendor files, firmware or LineageOS
tree is imported by this stage; default `seventeen` remains untouched.

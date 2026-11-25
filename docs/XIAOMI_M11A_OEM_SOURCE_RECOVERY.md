# Xiaomi M11A: OEM-only source recovery and independent AOSP 17 panel bring-up

**Device:** POCO F5 Pro / Redmi K60, `mondrian`, SM8475 (Cape / Snapdragon 8+ Gen 1).

**Rule:** PixelExperience-Reborn AOSP 17 uses the Xiaomi OEM-released kernel and DTS sources, plus selectively adapted official Qualcomm driver interfaces. **LineageOS code, panel descriptions and complete device trees must not be imported.** Other ROMs may be inspected to understand potential engineering gaps; they never establish panel values or become implementation sources.

## Source availability, independently checked

- Xiaomi's public `MiCode/kernel_devicetree`, branch `mondrian-s-oss`, selected commit `34e6cc7d832ed9c655b9d79bc3ffe1d625146b7c`, provides the existing seven selected OEM files, Cape base DTB inputs and the `mondrian-sm8475-pm8008-overlay.dts` board wrapper.
- That published branch **does not provide** `qcom/display/display/mondrian-sde-display-mtp.dtsi` or `qcom/display/display/dsi-panel-m11a-42-02-0a-dsc-cmd.dtsi` at the inspected paths. The existing Xiaomi board wrapper does not define the panel timing, LHBM or FOD commands.
- The imported Goodix device-tree properties and board selection are already separately source-locked. Do not infer panel readiness from successful fingerprint or Cape DTB syntax.
- The separate Qualcomm WAIPIO SDE/DSI source in [Kernel Display PR #4](https://github.com/PixelExperience-Reborn/android_kernel_xiaomi_sm8450/pull/4) has a successful [real `msm_drm.ko` MODPOST/ABI build](https://github.com/PixelExperience-Reborn/android_kernel_xiaomi_sm8450/actions/runs/43607464216); this does **not** supply the missing manufacturer M11A data.

## Published mondrian display source and compiled candidate

Xiaomi also published the SM8475 display controllers and the actual mondrian M11A board, panel and timings in its separate display-devicetree repository. The selected revision is on the `garnet-t-oss` branch. The PE input includes the Xiaomi **mondrian** board file and the Cape display controllers. The PE wrapper sets M11A as the primary fallback specifically in this diagnostic build. The bootloader panel override takes precedence in the DSI driver. [MiCode mondrian board](https://github.com/MiCode/vendor_qcom_proprietary_display-devicetree/blob/ab5bc7b921d3d4072ce11eecfde984382e3ec695/display/mondrian-sde-display-mtp.dtsi)

The normal camera and three-repository builds also apply both display overlays to the camera-integrated `cape`, `cape-v2` and `capep` DTBs. The compiled panel ID is `0x4d31314100420200`. Each variant links the M11A supply table and exposes 1440 × 3200 at 60, 90 and 120 Hz with 720 × 32 DSC slices.

The global MIUI V14.0.5.0.TMNMIXM and HyperOS OS3.0.5.0.VMNMIXM board entries agree on the panel ID, rail settings, PHY timings, DSC geometry and four-frame FOD readiness delay. In the published 90 Hz ON table the two-byte length of the 0x5F packet was missing its high byte. The PE patch restores its 0x00 high byte. All three modes now decode to 57 packets and retain the 120 ms delay after Sleep Out before Display On. The corresponding firmware sequences have 111 and 135 packets. The installed revision is unknown. [Firmware entry hashes](MONDRIAN_STOCK_CAMERA_ROUTING.md)

In normal display operation the PE patch restores the same two page-select/register packets used in both firmware entries before white 1000/110 nit, green 500 nit, off-to-normal and off-to-HBM. It relocates the register-update indices with their packets. Each of the five command payloads and its LP/HS transmission mode matches both global versions at 60/90/120 Hz. For normal and low-power white 110 nit, register 0x87 has two data bytes. The PE update descriptors use two, including the low-power command variants with different indices at 120 Hz. The standalone build rejects update descriptors that exceed their packet's data, select the wrong register or leave an incomplete DSI header.

Xiaomi's M11A hardware path calculates alpha from panel brightness, applies calibration, sends the brightness command and delays the FOD-ready notification by the configured number of frames at the current refresh rate. Release clears readiness and selects the appropriate off transition. The diagnostic overlay enables the native M11A consumer in the paired PE kernel. It uses the per-unit calibration from SMEM for white capture and publishes FOD readiness after successful DSI transfer and four frame periods. Panel shutdown, ESD and release revoke readiness. The Xiaomi display class matches the stock ueventd subsystem. AOSP 17 service permissions and physical operation still need qualification. The board overlay uses the matching MIUI and HyperOS packets for white 1000/110 nit from doze, return to high/low doze, both doze brightness levels and exit from doze at all three rates. The two white sequences retain the 42 ms wait. [Xiaomi M11A calibration](https://github.com/MiCode/vendor_opensource_display-drivers/blob/bf0d5e23be5457001a18aa9dcd68cb17994ae36a/msm/mi_disp/mi_dsi_panel.c) · [Xiaomi FOD worker](https://github.com/MiCode/vendor_opensource_display-drivers/blob/bf0d5e23be5457001a18aa9dcd68cb17994ae36a/msm/mi_disp/mi_disp_lhbm.c)

## OEM-first recovery procedure

1. Start with an **official Xiaomi stock fastboot firmware archive for the exact mondrian SKU/region** from Xiaomi's distribution portal, or read the equivalent partition from the owner's unmodified stock installation. Record build number, model/region, source URL and cryptographic SHA256 of the original firmware archive. A user-entered filename or checksum is **not** independent provenance verification.
2. Confirm **both** `images/dtbo.img` and, when present, `images/vendor_boot.img` in the manufacturer package. Keep the original package and hashes outside the PE-Reborn Git tree. Per AOSP 17 [vendor_boot v3/v4 header layout](https://android.googlesource.com/platform/system/tools/mkbootimg/+/refs/heads/android17-release/include/bootimg/bootimg.h), a vendor boot image can carry a separate, page-aligned DTB section; the script parses only that section (never the ramdisk). Absence of a panel property in `dtbo.img` **does not** prove the factory build has no panel definition.
3. Install `device-tree-compiler` (`dtc`) and download the **Xiaomi-hosted Fastboot archive matching the exact device SKU and region**. For example, a `mondrian_global_images_...` package is not interchangeable with `mondrian_eea_global_images_...` without variant checks. Do **not** flash anything.
   ```bash
   # Original full Xiaomi Fastboot archive, kept outside our Git repository
   sha256sum /path/to/mondrian_global_images_...tgz

   # Read-only streaming inspection: images/dtbo.img and optional vendor_boot.img
   python3 tools/audit_xiaomi_fastboot_package.py \
       --fastboot-tgz /path/to/mondrian_global_images_...tgz \
       --expected-sha256 <FULL_SHA256_OF_DOWNLOADED_TGZ> \
       --out /tmp/pe-mondrian-stock-dtbo-audit
   ```
   This **does not require extracting the whole Xiaomi Fastboot package**. The script checks the expected SHA-256 against the entire local archive, rejects non-`mondrian` archive roots, unsafe member paths, links, duplicate DTBO/vendor_boot members, malformed Android DT tables, unsupported vendor_boot headers and FDT bounds, and stores only JSON hashes and candidate feature-presence flags. The final JSON report is replaced atomically **only after both partitions pass**: an invalid vendor_boot never leaves a partial report or overwrites previous evidence. It deletes the temporary local DTBO copy after analysis. `vendor_boot.img` is read only into bounded memory; it is not left on disk, and the vendor ramdisk is neither extracted nor decompressed.
   
   The resulting `xiaomi-stock-dtbo-diagnostic.json` has an optional `stock_vendor_boot` section: `present`, `embedded_dtb_count`, header version, per-DTB hashes and panel property-presence indicators. A zero count or absent vendor_boot is normal *diagnostic* evidence, not an assertion about the actual M11A panel. We still need the exact manufacturer's board/panel revision and source audit before native implementation.

   For each real FDT, the separate [stock panel structure audit](../tools/audit_xiaomi_panel_evidence.py) also reports candidate panel names, the manufacturer-encoded `mi,panel-id` when present, numeric refresh/size/DSC parameters and whether the basic DSC geometry is internally consistent. These values are reported **only when found in that particular supplied Xiaomi DTB**. The structural parser rejects invalid FDT token/offset/padding combinations, checks the DTSpec v17 memory reservation map's bounded 64-bit entries and zero/zero terminator, and keeps all actual DCS, init, doze and LHBM command payloads out of JSON and out of our source tree. An absent panel or an apparently valid DSC layout is **not** automatic Xiaomi firmware authenticity or device revision verification.
   
   If an authentic `dtbo.img` has *already* been extracted separately from Xiaomi stock firmware, the original diagnostic entry point also remains available:
   ```bash
   python3 tools/audit_xiaomi_stock_dtbo.py \
       --dtbo /path/to/xiaomi-stock/images/dtbo.img \
       --package-sha256 <FULL_SHA256_OF_ORIGINAL_STOCK_ARCHIVE> \
       --out /tmp/pe-mondrian-stock-dtbo-audit
   ```
   **Important provenance limit:** comparing an archive to a SHA-256 typed by the same operator verifies file integrity only; it is **not independent manufacturer signature verification**. Keep the original Xiaomi download host, ROM version/region and independently trusted metadata. Neither helper imports foreign panel code, writes proprietary DCS sequences into our Git repository, produces production `dtbo.img`, or authorizes a hardware claim.
4. Confirm extracted evidence against *matching original Xiaomi* panel revision/SKU/board selection and, when available, Qualcomm's published bindings and kernel driver. Check real DSC parameters, DSI PHY rates/lanes, regulator power order, ESD, brightness, doze, UDFPS-local HBM command transitions and panel readiness events.
5. Independently implement a **native mondrian panel definition** compatible with the selected OEM kernel, exact Qualcomm SDE/DSI and Android 17 userspace. Keep provenance, reviewed adaptation diffs, real test cases and actual hardware validation. No placeholder DCS commands or forced feature-disable are permitted.
6. Only after OEM source authenticity, panel revision and all dependencies are proven: review the `oem-m11a-panel-source-lock.json` gate and approve changes to shipping DTS/build scripts. Re-run actual Cape/board `fdtoverlay`, `msm_drm.ko`/KMI, Goodix UDFPS/LHBM, module load order, AOSP17 HWC/VINTF/SELinux and real mondrian tests.

## DTBO format handling from official AOSP

The manufacturer `dtbo.img` must be interpreted with the AOSP `dt_table_header` and per-entry metadata, not by matching strings in the raw compressed partition. As documented by [AOSP DTB/DTBO partitions](https://source.android.com/docs/core/architecture/dto/partitions) and the [official `mkdtboimg.py` table encoder](https://android.googlesource.com/platform/system/libufdt/+/refs/heads/main-kernel-2025/utils/src/mkdtboimg.py), the read-only Xiaomi analyzer accepts valid **v0, v1 and v2** table layouts (32/32/64-byte entries, respectively). The diagnostic JSON preserves each entry's `id`, `rev`, `custom[]`, table version, flags and compression type as reported; the bootloader SKU match is **not inferred** from those numbers without independent OEM evidence. The FDT panel evidence separately preserves only whitelisted root `compatible`, `qcom,msm-id`, `qcom,board-id` and `xiaomi,miboard-id` cells, if present, with the explicit flag `stock_board_revision_verified=false`. These selectors can be compared against the pinned Xiaomi `mondrian-sm8475-pm8008-overlay.dts` by an engineer, but a matching number alone does **not** establish correct OLED revision or manufacturer authenticity.

For v1/v2 compressed FDT entries, bounded decompression is available for zlib/gzip. Optional **LZ4 frame** handling requires `python3 -m pip install lz4` in the local audit environment; the analyzer fails closed if that dependency is absent. Compressed data must decode to a valid FDT, with no hidden trailing nonzero data. Read-only extraction does not establish authenticity, matching `mondrian` panel revision, physical 60/90/120 Hz capability, UDFPS LHBM behavior or production eligibility. The real stock Xiaomi Fastboot input remains a required separate step.

## Fail-closed status

The `oem-m11a-panel-source-lock.json` record has `product_selection_allowed: false`. CI tests reject unreviewed M11A DTS staging until the factory command revision and hardware results are known. The audit helper is **diagnostic only**, and a panel marker in any DTB does not prove it matches the particular phone or firmware. No `dtbo.img` or flashable ROM is produced by this stage.

**Still out of scope:** Camera, Video, Audio and other hardware dependencies. Production `seventeen` is unchanged.

## 15 Nov 2026 — DSC structural validation aligned to pinned OEM/Qualcomm kernel

The stock FDT diagnostic now follows the accepted DSC input bounds of
`PixelExperience-Reborn/android_kernel_xiaomi_sm8450@fa31740dec88f048165420a269ae4cb10e97e2f0`,
which has already passed its real OEM `vmlinux` + Qualcomm `msm_drm.ko`
compile. In particular, `dsc_slice_height = 1` must be rejected before
the kernel's `slice_height - 1` divisor. Reject unsupported 1.1/1.2
versions, SCR revisions, component depths and integer bpp combinations not
present in Qualcomm's rate-control tables; geometry rejection is not a
positive panel-identification result. These checks are diagnostic only and
do not manufacture M11A/R66451 DCS/DSC data. Source and DTBO compile CI
must pass before declaring this gate qualified.

## Manufacturer DSC rate-control compatibility gate

Pinned against OEM/Qualcomm Kernel `fa31740dec88f048165420a269ae4cb10e97e2f0`,
the read-only FDT analyzer now accepts only the exact DSC version, chroma
sampling, bit-depth and bitrate tuples in `msm/sde_dsc_helper.c`
(`sde_dsc_index_map`). The `qcom,src-chroma-format` value is captured
as a whitelisted numeric field: Qualcomm `msm_drv.h` defines RGB 444 as
0, 422 as 1, and 420 as 2, and `dsi_panel.c` defaults to 444 when it is
absent. Unknown formats and odd-width subsampled slices fail closed.
A result indicating structurally supported rate control is **not** a
manufacturer panel identity check, does not enable LHBM and cannot approve
a production DTBO. No proprietary DCS payloads are exported.

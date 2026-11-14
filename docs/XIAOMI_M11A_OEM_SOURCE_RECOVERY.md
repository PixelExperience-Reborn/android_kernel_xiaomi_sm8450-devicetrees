# Xiaomi M11A: OEM-only source recovery and independent AOSP 17 panel bring-up

**Device:** POCO F5 Pro / Redmi K60, `mondrian`, SM8475 (Cape / Snapdragon 8+ Gen 1).

**Rule:** PixelExperience-Reborn AOSP 17 uses the Xiaomi OEM-released kernel and DTS sources, plus selectively adapted official Qualcomm driver interfaces. **LineageOS code, panel descriptions and complete device trees must not be imported.** Other ROMs may be inspected to understand potential engineering gaps; they never establish panel values or become implementation sources.

## Source availability, independently checked

- Xiaomi's public `MiCode/kernel_devicetree`, branch `mondrian-s-oss`, selected commit `34e6cc7d832ed9c655b9d79bc3ffe1d625146b7c`, provides the existing seven selected OEM files, Cape base DTB inputs and the `mondrian-sm8475-pm8008-overlay.dts` board wrapper.
- That published branch **does not provide** `qcom/display/display/mondrian-sde-display-mtp.dtsi` or `qcom/display/display/dsi-panel-m11a-42-02-0a-dsc-cmd.dtsi` at the inspected paths. The existing Xiaomi board wrapper does not define the panel timing, LHBM or FOD commands.
- The imported Goodix device-tree properties and board selection are already separately source-locked. Do not infer panel readiness from successful fingerprint or Cape DTB syntax.
- The separate Qualcomm WAIPIO SDE/DSI source in [Kernel Display PR #4](https://github.com/PixelExperience-Reborn/android_kernel_xiaomi_sm8450/pull/4) has a successful [real `msm_drm.ko` MODPOST/ABI build](https://github.com/PixelExperience-Reborn/android_kernel_xiaomi_sm8450/actions/runs/43607464216); this does **not** supply the missing manufacturer M11A data.

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
   This **does not require extracting the whole Xiaomi Fastboot package**. The script checks the expected SHA-256 against the entire local archive, rejects non-`mondrian` archive roots, unsafe member paths, links, duplicate DTBO/vendor_boot members, malformed Android DT tables, unsupported vendor_boot headers and FDT bounds, and stores only JSON hashes and candidate feature-presence flags. It deletes the temporary local DTBO copy after analysis. `vendor_boot.img` is read only into bounded memory; it is not left on disk, and the vendor ramdisk is neither extracted nor decompressed.
   
   The resulting `xiaomi-stock-dtbo-diagnostic.json` has an optional `stock_vendor_boot` section: `present`, `embedded_dtb_count`, header version, per-DTB hashes and panel property-presence indicators. A zero count or absent vendor_boot is normal *diagnostic* evidence, not an assertion about the actual M11A panel. We still need the exact manufacturer's board/panel revision and source audit before native implementation.
   
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

## Fail-closed status

The `oem-m11a-panel-source-lock.json` record has `product_selection_allowed: false`. CI tests reject unreviewed M11A DTS staging while the OEM inputs and hardware evidence are missing. The audit helper is **diagnostic only**, and a panel marker in any DTB does not prove it matches the particular phone or firmware. No `dtbo.img` or flashable ROM is produced by this stage.

**Still out of scope:** Camera, Video, Audio and other hardware dependencies. Production `seventeen` is unchanged.

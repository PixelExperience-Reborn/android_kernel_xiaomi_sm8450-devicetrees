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
2. Locate `images/dtbo.img` in the manufacturer package. Keep the original and hashes outside the PE-Reborn Git tree. Other board descriptions may be stored in the stock boot/vendor_boot images; absence from `dtbo.img` alone is **not** evidence that the panel does not exist.
3. Install `device-tree-compiler` (`dtc`). Execute the read-only audit:
   ```bash
   sha256sum mondrian_stock_fastboot.tgz
   python3 tools/audit_xiaomi_stock_dtbo.py \
       --dtbo /path/to/official_xiaomi/images/dtbo.img \
       --package-sha256 <SHA256_OF_THE_ORIGINAL_STOCK_ARCHIVE> \
       --out /tmp/pe-mondrian-stock-dtbo-audit
   ```
   The script validates the Android DT table and FDT boundaries, decompiles **in memory** using `dtc`, and stores only JSON hashes and candidate feature-presence flags. It does **not** copy a third-party panel tree, dump proprietary DCS commands into the repository, produce a `dtbo.img` or assert manufacturer authenticity.
4. Confirm extracted evidence against *matching original Xiaomi* panel revision/SKU/board selection and, when available, Qualcomm's published bindings and kernel driver. Check real DSC parameters, DSI PHY rates/lanes, regulator power order, ESD, brightness, doze, UDFPS-local HBM command transitions and panel readiness events.
5. Independently implement a **native mondrian panel definition** compatible with the selected OEM kernel, exact Qualcomm SDE/DSI and Android 17 userspace. Keep provenance, reviewed adaptation diffs, real test cases and actual hardware validation. No placeholder DCS commands or forced feature-disable are permitted.
6. Only after OEM source authenticity, panel revision and all dependencies are proven: review the `oem-m11a-panel-source-lock.json` gate and approve changes to shipping DTS/build scripts. Re-run actual Cape/board `fdtoverlay`, `msm_drm.ko`/KMI, Goodix UDFPS/LHBM, module load order, AOSP17 HWC/VINTF/SELinux and real mondrian tests.

## Fail-closed status

The `oem-m11a-panel-source-lock.json` record has `product_selection_allowed: false`. CI tests reject unreviewed M11A DTS staging while the OEM inputs and hardware evidence are missing. The audit helper is **diagnostic only**, and a panel marker in any DTB does not prove it matches the particular phone or firmware. No `dtbo.img` or flashable ROM is produced by this stage.

**Still out of scope:** Camera, Video, Audio and other hardware dependencies. Production `seventeen` is unchanged.

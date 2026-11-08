# mondrian SM8475 — independent PE-Reborn DT/DTBO qualification

**State:** source-only, no DT/DTBO imported, built or boot-tested.
The public LineageOS DT repository is a reference to historical Qualcomm
SM8475/Xiaomi hardware wiring. It is **not** our production source or ROM base.

## Pinned reference boundaries

The machine-readable `dtbo-bsp-candidates.json` records a Git commit and
distinct Git root tree plus five file blobs inspected on 2026-11-08.
The sources must be evaluated with the eventual kernel's device tree
compiler, DTS preprocessing and bootloader support; a matching path does
not establish build/boot compatibility.

1. Base DTBs: `cape.dtb`, `cape-v2.dtb`, `capep.dtb`.
2. Board overlay: `mondrian-sm8475-pm8008-overlay.dtbo`.
3. Display overlay: `mondrian-sde-display-mtp-overlay.dtbo`; M11A panel
   include `dsi-panel-m11a-42-02-0a-dsc-cmd.dtsi`.
4. Camera overlay: `mondrian-sm8475-camera-sensor.dtbo`.
5. Board DTS includes `mondrian-pinctrl.dtsi` and
   `xiaomi-sm8475-common.dtsi`, requiring their full transitive includes.

## Touch/UDFPS: incompatibility is explicitly blocked

The reference board DTS declares `goodix,gt9916S` on SPI with
`goodix_firmware_m11a.bin` and `goodix_cfg_group_m11a.bin`.
The manufacturer Goodix driver matches `goodix,brl-d` instead, so a
driver file copy may fail DT binding. Do not rewrite `compatible` without
reconciling protocol, IRQ/reset/regulators, ESD/recovery, firmware version
and device identification.

A separate `goodix,fingerprint` node does **not** imply touchscreen
and UDFPS share a kernel driver. Fingerprint HAL/TEE, FOD and M11A panel
brightness must be qualified together on physical mondrian.

## Required integration gates

- Pin selected kernel/modules/DT commits in one reproducible manifest.
- Validate every DTS include, phandle, regulator and pinctrl binding.
- Compile every required DTB/DTBO using the selected kernel's dtc toolchain.
- Apply every overlay to all applicable base DTBs with `fdtoverlay`.
- Confirm board-id and overlay selection against this actual phone and
  both POCO F5 Pro / Redmi K60 variants.
- Verify panel power modes, refresh rates, display HBM/FOD, touch
  input/ESD/resume, cameras, audio and suspend/resume in a real build.
- Never install opaque or other-device DTBO binaries as a substitute
  for this source qualification.

The platform stays independent AOSP 17; no FM radio or inherited
LineageOS product packages are permitted. Hardware acceptance is
**NOT PROVEN** by these host-only metadata checks.

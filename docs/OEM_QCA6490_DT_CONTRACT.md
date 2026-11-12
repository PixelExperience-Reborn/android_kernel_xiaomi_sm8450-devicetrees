# Xiaomi QCA6490 / Cape Device Tree compatibility — mondrian

This source contract checks the **official Xiaomi** `MiCode/kernel_devicetree@34e6cc7d` `cape.dtsi` Wi-Fi/PCIe node against our independently compiled Qualcomm OEM WLAN path. Device is `mondrian` (SM8475) only.

- Board `compatible = "qcom,cnss-qca6490"` is required, with exactly one CNSS target node per merged Cape DTB.
- Xiaomi's WLAN enable GPIO 80, BT enable GPIO 81, software control GPIO 82, WLAN PCIe RC 0, ramdump memory configuration, five WLAN regulator references and antenna switch regulator must all be present.
- The checkout source test validates numeric GPIOs and root source origin, while the binary build checks the corresponding properties survive compilation and applying the mondrian board overlay to each of `cape`, `cape-v2` and `capep`.
- No QCA6490 board DTS, regulators, GPIO number or timing has been modified. The existing Goodix adaptations are unchanged.
- [Our OEM kernel and QCACLD build](https://github.com/PixelExperience-Reborn/android_kernel_xiaomi_sm8450-modules/actions/runs/43088150435) passed the Clang23 source/KMI compile gate, but hardware device-tree binding and firmware loading are **not** yet verified.

This is an intermediate binding/DTBO qualification. Final AOSP17 PE-Reborn `vendor_boot` / `vendor_dlkm` placement, wlan firmware, BT-coexistence, thermal behavior, SELinux, physical RF and boot still require independent checks. No FM radio or LineageOS source is added.

## OEM Goodix under-display fingerprint binding

The same manufacturer-provided `qcom/mondrian-sm8475.dtsi` has `fingerprint_goodix` with `compatible="goodix,fingerprint"`, reset GPIO 41, IRQ GPIO 40 and regulator `L9C` at 3.2 V. Our pinned OEM kernel `2466406` enables `CONFIG_FINGERPRINT_GOODIX_FOD_G3S=m`; `goodix_fod_G3S/gf_spi.c` matches `goodix,fingerprint` and regulator name `l9c_vdd`, while `goodix_fod_G3S/platform.c` reads `goodix,gpio-reset` / `goodix,gpio-irq`. The DTB test requires these fields in every merged Cape + mondrian binary.

This proves source and compiled-DTB **binding consistency only**. Fingerprint firmware, TEE, biometric HAL, screen illumination, touch/display panel sync, SELinux and on-device authentication remain unverified. No new kernel driver or substitute ROM module is introduced.

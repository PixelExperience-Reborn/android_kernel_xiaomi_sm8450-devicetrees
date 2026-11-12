# Xiaomi QCA6490 / Cape Device Tree compatibility — mondrian

This source contract checks the **official Xiaomi** `MiCode/kernel_devicetree@34e6cc7d` `cape.dtsi` Wi-Fi/PCIe node against our independently compiled Qualcomm OEM WLAN path. Device is `mondrian` (SM8475) only.

- Board `compatible = "qcom,cnss-qca6490"` is required, with exactly one CNSS target node per merged Cape DTB.
- Xiaomi's WLAN enable GPIO 80, BT enable GPIO 81, software control GPIO 82, WLAN PCIe RC 0, ramdump memory configuration, five WLAN regulator references and antenna switch regulator must all be present.
- The checkout source test validates numeric GPIOs and root source origin, while the binary build checks the corresponding properties survive compilation and applying the mondrian board overlay to each of `cape`, `cape-v2` and `capep`.
- No QCA6490 board DTS, regulators, GPIO number or timing has been modified. The existing Goodix adaptations are unchanged.
- [Our OEM kernel and QCACLD build](https://github.com/PixelExperience-Reborn/android_kernel_xiaomi_sm8450-modules/actions/runs/43088150435) passed the Clang23 source/KMI compile gate, but hardware device-tree binding and firmware loading are **not** yet verified.

This is an intermediate binding/DTBO qualification. Final AOSP17 PE-Reborn `vendor_boot` / `vendor_dlkm` placement, wlan firmware, BT-coexistence, thermal behavior, SELinux, physical RF and boot still require independent checks. No FM radio or LineageOS source is added.

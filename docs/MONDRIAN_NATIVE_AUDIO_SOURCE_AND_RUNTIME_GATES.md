# Mondrian native Audio — source and compiled-board gate (AOSP 17)

**Scope:** POCO F5 Pro / Redmi K60 (mondrian, SM8475), OEM Xiaomi 5.10.81
kernel. This is an independent PixelExperience-Reborn source audit, not
a LineageOS import and not a product Audio implementation.

## Original Xiaomi hardware actually established

From the pinned manufacturer `MiCode/kernel_devicetree`
`34e6cc7d832ed9c655b9d79bc3ffe1d625146b7c`:

* `qcom/mondrian-sm8475.dtsi`: two `awinic,aw882xx_smartpa`
  speakers on `qupv3_se15_i2c`, at addresses **0x34** (channel 0,
  IRQ TLMM88, reset TLMM1, speaker switch TLMM52) and **0x35**
  (channel 1, IRQ TLMM63, reset TLMM3). No other device board data
  is needed for these assertions.
* Same OEM board: MI2S2/TDM source pins **GPIO122=data0**,
  **GPIO124=data1**, **GPIO121=SCK**, **GPIO123=WS**.
* `qcom/mondrian-pinctrl.dtsi` has legacy `cirrus_*` labels for
  overlapping pins, but those labels do **not** authorize selecting
  Cirrus audio amplifiers or rewriting the OEM AW882xx device nodes.

`tools/verify_mondrian_audio_fdt.py` audits these exact connections
**after** building and merging the original Cape, Cape-v2, and Capep
DTBs with the selected mondrian board overlay. It checks resolved I2C
and TLMM symbols, address/channel consistency, GPIO provider phandles,
and the four MI2S2 mux assignments. It does not modify the original
manufacturer sources. Negative tests reject donor/wrong board values.

The resulting `dtbo-diagnostic-evidence.json` contains
`mondrian_oem_audio_compiled_evidence` for all three Cape bases.
This is a **diagnostic compiled hardware description**, never a
flashed `dtbo.img`.

## Still blocking an actual Audio milestone

1. Identify a compatible Qualcomm **WAIPIO/SM8475** audio-kernel
   source revision and original Awinic AW882xx codec source. The
   selected OEM kernel has no ready AW882xx / WAIPIO audio machine
   implementation in its currently qualified kernel module inventory.
2. Compile Audio kernel/codec modules against the same OEM vmlinux,
   `Module.symvers` and LLVM 23 as Camera, Display and WLAN.
   Verify dependencies, exported symbols, vermagic and genuine
   device-specific DSP/machine configuration before adding to any
   production module-loading list.
3. Independently adapt Audio userspace HAL/ALSA topology and original
   mondrian calibration for AOSP 17. Do not guess amplifier voltages,
   channels, runtime controls or firmware; do not copy LineageOS code.
4. Finally validate speakers, microphones, receiver, wired/USB audio,
   call routing, suspend/resume, thermal limits and DSP on the real
   mondrian.

**Important:** Source-only or compiled-FDT tests must never set
`audio_driver_abi_verified`, `audio_hal_verified`,
`physical_audio_tested`, or `production_audio_approved` to true.
This stage changes neither OEM kernel, factory pin assignments,
production device trees, nor Camera/LHBM/UDFPS.

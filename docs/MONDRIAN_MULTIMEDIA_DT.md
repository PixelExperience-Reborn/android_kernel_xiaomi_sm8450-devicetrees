# Mondrian audio and video device tree

Xiaomi publishes the mondrian base and board DT (`MiCode/kernel_devicetree`,
`mondrian-s-oss`) plus display and camera DT, but not the WAIPIO audio, video
or MMRM device trees. None of the nine Xiaomi WAIPIO/CAPE branches (mondrian,
diting, mayfly, zeus, liuqin, yudi, marble, ziyi, garnet) contains them; they
all carry the same `waipio-audio-overlay.dtsi`, which references labels
(`lpass_cdc`, `spf_core_platform`, `waipio_snd`) from Qualcomm's base audio DT.
The original source is therefore Qualcomm CodeLinaro, pinned in
`qualcomm-multimedia-dt-source-lock.json`.

## Audio

- Qualcomm `audio-devicetree` `50ccb9f` (2022-03-03), the last commit before
  the `LA.VENDOR.1.0.r1-11900-WAIPIO.0` release (2022-03-14) that Xiaomi's
  5.10.81 kernel is built on.
- Xiaomi's `waipio-audio-overlay.dtsi` (blob `324f5d0`) replaces Qualcomm's in
  a temporary copy. It is Qualcomm's overlay with the factory mondrian changes:
  2750 mV micbias, three LPASS macros, WSA speakers disabled.
- `<bindings/...>` includes resolve through `include/bindings/`, which forward
  to the kernel `dt-bindings` headers. Their `#define` values are identical to
  the selected Xiaomi audio-kernel headers.
- `qcom/mondrian-audio-board-overlay.dts` wraps Qualcomm's CAPE MTP audio
  chain with the mondrian selector (msm-id 530/531/540, board-id 0x10008,
  miboard-id 0xE). AW882xx and MI2S2 remain in Xiaomi's `mondrian-sm8475.dtsi`.

## Video

Qualcomm `video-devicetree` `7c85d65` (tag `LA.VENDOR.15.4.1.r1-07900-WAIPIO.0`)
is the only public WAIPIO video DT in the legacy `qcom,msm-vidc` binding
(`qcom,msm-vidc-waipio`, `qcom,msm-vidc-iris2`, context banks) that the
release video driver `8608fb2` reads. The newer public files use
`qcom,sm8450-vidc`, which no WAIPIO 5.10 video driver matches. Every
driver-specific property (`clock-ids`, `qcom,allowed-clock-rates`,
`qcom,bus-range-kbps`, `qcom,reg-presets`, `vidc,firmware-name`,
`virtual-addr-pool`, `pas-id`, ...) is parsed by `8608fb2`. Its
`waipio-vidc.dts` already lists the CAPE msm-ids.

## MMRM: intentionally not added

`mmrm-driver` `69e304b` indexes exactly five voltage corners (LOW_SVS, SVS,
SVS_L1, NOM, TURBO). The public Qualcomm MMRM DTs describe WAIPIO with six or
eight corners and WAIPIO coefficients; CAPE coefficients are not public.
Using them would mis-map the corners and miscompute peak current. All MMRM
clients fall back to plain clock control when MMRM is absent.

## Build

`tools/build_mondrian_multimedia.py` runs after `build_mondrian_m11a.py`. It
verifies the pins, compiles the SoC audio, SoC video and mondrian audio board
overlays, applies them to the three Cape DTBs, and checks the AudioReach sound
card, SPF, LPASS, WCD938x with the Xiaomi micbias, both AW882xx, and the WAIPIO
VIDC node with its context banks. The merged DTB root stays unchanged, because
fdtoverlay never applies an overlay's root properties; the board overlay
itself carries the bootloader selector.

## Driver coverage gate

`tools/verify_dt_driver_coverage.py` requires every enabled node with a
`compatible` in the full DTBs to have a driver: an in-tree driver whose Kbuild
object is enabled in the generated `.config`, an external module source, or an
enabled consumer driver that looks the node up by compatible. The remaining
nodes are listed with a reason in `dt-driver-coverage-allowlist.json`
(platform/CPU/firmware nodes, legacy Q6 audio nodes unused by AudioReach,
AMBA/SLIMbus ID-matched devices, Xiaomi debug variants and the unpublished
Xiaomi touch-feature and hardware-info drivers). Devices that must have a
driver are never allowed in that list. The gate runs in the coherent modules
build, where the kernel, its configuration and all external sources exist
together.

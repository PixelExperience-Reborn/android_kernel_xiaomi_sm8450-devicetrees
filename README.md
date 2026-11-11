# PixelExperience-Reborn — Xiaomi OEM mondrian kernel Device Trees

Independent AOSP 17 development for **POCO F5 Pro / Redmi K60 (SM8475/Cape)**. Based on the pinned **Xiaomi `mondrian-s-oss`** kernel Device Tree, not a LineageOS source import.

## Verified

- Six unmodified source blobs and three explicitly checked changes to the seventh board DTS for our Goodix Berlin GT9916S driver and the actual m11a firmware/config filenames.
- Exact upstream Xiaomi `kernel_devicetree` commit `34e6cc7d832ed9c655b9d79bc3ffe1d625146b7c` pinned as Git submodule.
- `cape.dtb`, `cape-v2.dtb`, `capep.dtb` and `mondrian-sm8475-pm8008-overlay.dtbo` **compiled** with the selected PE-Reborn OEM kernel headers.
- `fdtoverlay` successfully applied the board overlay to each of the three Cape bases; the compiled overlay's Xiaomi board ID and the merged Goodix node + firmware/config names are verified.
- [Compiled CI evidence](https://github.com/PixelExperience-Reborn/android_kernel_xiaomi_sm8450-devicetrees/actions/runs/43010141003). Retained diagnostic DTB artifact, **not** a flashable image.

## Not yet qualified

Display M11A and camera/audio overlays, final `dtbo.img` packaging and bootloader SKU selection, actual AOSP17 vendor firmware, SELinux/VINTF, Qualcomm external modules, and **physical boot**. Production and boot readiness are **not confirmed**.

## Reproduce

`git submodule update --init --recursive`, then:

`python3 tools/build_oem_dtbo.py --kernel /path/to/pinned-PE-OEM-kernel --out /tmp/mondrian-dt`

See `oem-source-lock.json`, `docs/OEM_DTB_BUILD.md`, and `docs/OEM_MONDRIAN_DTS_BRINGUP.md` for the reproducible pinned source and release gates.

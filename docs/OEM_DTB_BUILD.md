# OEM-only Device Tree build

This checkout pins Xiaomi kernel_devicetree (mondrian-s-oss) as a Git submodule at 34e6cc7d832ed9c655b9d79bc3ffe1d625146b7c. Initialize with git submodule update --init --recursive. The Xiaomi files checked in under `qcom/` and pinned in `oem-source-lock.json` override the corresponding paths in a temporary manufacturer source copy. A provenance test reverts every declared adaptation and checks the original Xiaomi blob, so no undeclared change is possible, and the build fails if a pinned copy is not read by the compiled board. The stock OS3 comparison behind the adaptations is in `MONDRIAN_STOCK_OS3_DT_RECONCILIATION.md`.

Use python3 tools/build_oem_dtbo.py --kernel /path/to/selected-PE-OEM-kernel --out /tmp/mondrian-dt. The script compiles cape.dtb, cape-v2.dtb, capep.dtb and the mondrian board overlay, then applies it to each candidate base. This is a diagnostic build, not a shippable dtbo.img. Display and camera overlays, packaging, firmware, signing and hardware validation remain separate gates.

The board DTB compilation, overlay application, Xiaomi board ID and merged Goodix firmware-name tests passed [CI #43010141003](https://github.com/PixelExperience-Reborn/android_kernel_xiaomi_sm8450-devicetrees/actions/runs/43010141003), which publishes diagnostics and SHA256 hashes. Production image packaging and device boot remain gated.

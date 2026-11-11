# OEM-only Device Tree build

This checkout pins Xiaomi kernel_devicetree (mondrian-s-oss) as a Git submodule at 34e6cc7d832ed9c655b9d79bc3ffe1d625146b7c. Initialize with git submodule update --init --recursive. The seven checked-in device files override the corresponding paths in a temporary manufacturer source copy. A provenance test verifies the sole adaptation of the SPI Goodix compatible string.

Use python3 tools/build_oem_dtbo.py --kernel /path/to/selected-PE-OEM-kernel --out /tmp/mondrian-dt. The script compiles cape.dtb, cape-v2.dtb, capep.dtb and the mondrian board overlay, then applies it to each candidate base. This is a diagnostic build, not a shippable dtbo.img. Display and camera overlays, packaging, firmware, signing and hardware validation remain separate gates.

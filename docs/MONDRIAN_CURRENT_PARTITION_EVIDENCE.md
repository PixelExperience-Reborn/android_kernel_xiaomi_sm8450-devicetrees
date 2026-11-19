# mondrian — current partitions Camera evidence (read-only)

This is a diagnostic for PixelExperience-Reborn AOSP 17, SM8475 mondrian.
The phone collector collect_mondrian_hardware_evidence.sh produced a tar.gz
archive of the CURRENT active DTBO and vendor_boot. Those may contain a
custom ROM, and must NOT be used as proof of original Xiaomi firmware.

## Offline host analysis

Install Python 3 and dtc (device-tree-compiler). Transfer the archive from
the phone to a trusted computer. From the Devicetrees repository, run:

    python3 tools/audit_mondrian_current_partitions.py \
      --archive /path/to/mondrian_readonly_evidence_20261119_160807.tar.gz \
      --out /path/to/mondrian-current-evidence

The report is mondrian-current-partitions-camera-diagnostic.json.
The tool never extracts or flashes images. It verifies manifest hashes,
slot/device metadata, archive member safety, FDT structures, and lists
candidate Camera flash wiring, panel structures and raw board IDs.
Unresolved FDT fixups remain unresolved. All production qualification flags
stay false. Integrity within the archive is NOT manufacturer authenticity.

No sensor, GPIO, PMIC channel, regulator, camera HAL, boot image or product
DTBO is enabled or modified. Do not upload raw partitions to a public repo.

## Next manufacturer gate

Use the exact SKU/region ORIGINAL Xiaomi Fastboot firmware, independently
check its source and SHA256, and run tools/audit_xiaomi_fastboot_package.py.
Only then compare the manufacturer DTBO/vendor_boot structures with the
current partition report. Confirm CCI/CSI, EEPROM, actuator, power sequencing,
PM8350C flash and physical tests independently before enabling Camera.

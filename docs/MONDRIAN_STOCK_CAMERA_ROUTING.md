# POCO F5 Pro global camera wiring

The native board overlay targets Xiaomi board 14 (board ID 0x10008, subtype 0). Two independently published extractions of global Xiaomi firmware carry the same sensor, EEPROM, flash and shared power wiring. The SHA-256 digests identify the original binary FDT entries, before inspection. The signatures of the complete Xiaomi release packages have not been verified here.

| Global build | Binary entry | SHA-256 |
| --- | --- | --- |
| MIUI V14.0.5.0.TMNMIXM | [Mondrian DTB, entry named 21](https://github.com/Klozz/poco_mondrian_dump/blob/72d902d1eab5d87055a40f84a90eaecf74a9b8ae/dtbo/21_dtbdump_Mondrian_based_on_Qualcomm_Technologies%2C_Inc_SM8475.dtb) | `eeb595dd97f53c326ea7ac023df7af3195655178891302881273ae0cfa751553` |
| HyperOS OS3.0.5.0.VMNMIXM | [Mondrian DTB, entry named 20](https://github.com/Jiovanni-dump/poco_mondrian_dump/blob/763777736679fdac7d3e502a0b0caed36f435e7e/dtbo/20_dtbdump_Mondrian_based_on_Qualcomm_Technologies%2C_Inc_SM8475.dtb) | `9f9e1b7a277dd84180c28c4af0b73c9607ae501c80958354a233b89c2921ff83` |

| Slot | Role | CCI parent | cci-device property | CCI master | CSIPHY | MCLK / reset (TLMM) | EEPROM | Flash cell |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | Wide, actuator 0 | 0 | absent | 1 | 2 | 102 / 126 | 0 | 1 |
| 1 | Front | 0 | 1 | 0 | 4 | 105 / 127 | 1 | none |
| 2 | Ultrawide | 0 | 1 | 0 | 1 | 101 / 24 | 2 | 2 |
| 3 | Macro | 1 | absent | 0 | 0 | 100 / 128 | 3 | 3 |

Both firmware entries attach all three rear flash cells to PM8350C flash0, torch0 and switch0. Switch0 selects bit 0. The common SM8475 board sets bits 0 and 3. Only the mondrian diagnostic layer overrides that mask.

The wide sensor shares reset, AVDD, DVDD and MCLK2. The resource manager describes TLMM lines 126, 70, 2 and 102 as controller-relative GPIO specifiers. The matching camera module resolves the lines at bind time. Both firmware entries set the ultra EEPROM reset index to 0 and the sensor reset index to 1 despite listing the same GPIOs. Preserve that distinction for bench verification before product use.

The build links this overlay after the Cape camera controllers on each original mondrian base. Hardware qualification still requires the actual sensor IDs, successful EEPROM reads, autofocus, camera power cycles and PM8350C torch/flash operation through the camera HAL.

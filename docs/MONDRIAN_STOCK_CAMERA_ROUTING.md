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

The wide sensor shares reset, AVDD, DVDD and MCLK2. The resource manager describes TLMM lines 126, 70, 2 and 102 as controller-relative GPIO specifiers. The matching camera module resolves the lines at bind time.

## Factory Camera HAL profiles

| CamX camera ID | Sensor | Factory variants | Sensor ID register → expected value | EEPROM |
| --- | --- | --- | --- | --- |
| 0 | OV64B40 | Sunny I, AAC II | 0x300a → 0x5664 | GT24P128E |
| 1 | OV16A1Q | OFilm I, AAC II | 0x300b → 0x1641 | GT24P64E |
| 2 | OV08D10 | OFilm I, Sunny II | 0x0000 → 0x5647 | P24C64F |
| 3 | OV02B10 | Sunny I | 0x0002 → 0x002b | GT24P64E |

These are the physical probe profiles declared by CamX. Each binary's `cameraModuleData` references a `moduleConfiguration` with the camera ID and sensor, EEPROM and accessory names. The sensor driver record supplies the ID register and expected response. All seven decoded assignments match across the two global vendor releases below. The profile list records the original Git blob hashes and CamX 8-bit wire addresses. The build report associates these IDs with the corresponding compiled sensor and EEPROM nodes on each Cape base. [MIUI V14.0.5.0.TMNMIXM](https://github.com/Klozz/poco_mondrian_dump/tree/72d902d1eab5d87055a40f84a90eaecf74a9b8ae/vendor/lib64/camera) · [HyperOS V816.0.8.0.UMNMIXM](https://github.com/gm-stuffs/poco_mondrian_dump/tree/08d057dfd16a6b2c8520100290d4b1807b03ce86/vendor/lib64/camera) · [Machine-readable profiles](../mondrian-camera-hal-profiles.json)

The Sunny and AAC wide profiles identify the DW9800V actuator and name an AK7323 OIS profile. All four CamX binaries (two modules × two releases) contain two zero-filled OIS power records and thirteen register-data records whose values are all zero. Neither board-14 firmware overlay provides a standalone OIS node or an `ois-src` link. Applying the HyperOS board entry to all three matching factory Cape bases also yielded no such endpoint. The Xiaomi sensor driver returns slot ID −1 in this case. The build preserves the wide actuator link and rejects a standalone wide OIS link in this board configuration. The physical control path and optical stabilization on the phone still require evidence. [Xiaomi sensor DT parsing](https://github.com/MiCode/vendor_qcom_opensource_camera-kernel/blob/9ed4ce96d49c0759c6365627113c5f59c2407942/drivers/cam_sensor_module/cam_sensor/cam_sensor_soc.c)

## Ultrawide EEPROM reset

In the OFilm and Sunny P24C64F records the entire power-up sequence is WL2866D AVDD1 on (type 15, value 1, delay 3 ms). Power-down is the same rail off (value 0, delay 0). Neither sequence contains a reset or MCLK command. These values come from the EEPROM driver record, independently of the sensor's own power sequence.

Both stock DT entries assign the EEPROM's reset to index 0, which is TLMM 101 (MCLK1). The diagnostic EEPROM node therefore omits the optional reset assignment. Its original GPIO requests and active/suspend pinctrl states still apply. The OV08D10 sensor has its own reset on index 1, TLMM 24. With the EEPROM reset property absent, the Xiaomi driver leaves that GPIO role invalid and skips explicit reset writes. [Xiaomi camera power and GPIO handling](https://github.com/MiCode/vendor_qcom_opensource_camera-kernel/blob/9ed4ce96d49c0759c6365627113c5f59c2407942/drivers/cam_sensor_module/cam_sensor_utils/cam_sensor_util.c)

The build links this overlay after the Cape camera controllers on each original mondrian base. Hardware qualification still requires the actual sensor IDs, successful EEPROM reads, autofocus, camera power cycles and PM8350C torch/flash operation through the camera HAL.

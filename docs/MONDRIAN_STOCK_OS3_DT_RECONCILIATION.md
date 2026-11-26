# Сверка device tree mondrian со стоком OS3.0.8.0.VMNCNXM

Эталон — дерево стоковой китайской прошивки OS3.0.8.0.VMNCNXM: базовые DTB Cape
из `vendor_boot` (cape 0x212, capep 0x213, cape-v2 0x21c) с наложенным
оверлеем mondrian из `dtbo` (запись 19: msm-id 530/531/540, board-id
`0x10008 0`). Наше дерево — полная цепочка сборки этого репозитория
(`build_oem_dtbo.py` → `build_mondrian_camera_platform.py` →
`build_mondrian_m11a.py` → `build_mondrian_multimedia.py`) на ядре
`2efda4cf1afa`. Сравниваются скомпилированные деревья, узел за узлом и
свойство за свойством.

Правило: стоковое значение принимается, только если драйвер **нашего**
ядра 5.10.81 или наших модулей его читает и ведёт себя так же. Иначе
расхождение остаётся и записывается сюда с причиной.

## Как вносятся изменения в файлы Xiaomi

Файлы Xiaomi (`MiCode/kernel_devicetree`, mondrian-s-oss) не правятся
молча. Наша копия лежит в `qcom/`, исходный git-blob закреплён в
`oem-source-lock.json`, а каждое изменение — «объявленная адаптация»:
`oem_binding` (фрагмент Xiaomi), `pe_binding` (наш фрагмент) и `reason`.
Тест `tests/test_oem_mondrian_source.py` откатывает адаптации и сверяет
blob, поэтому любая необъявленная правка ломает CI. `build_oem_dtbo.py`
дополнительно требует, чтобы каждая закреплённая копия реально читалась
препроцессором при сборке: копия, которую сборка не использует, — ошибка.

## Принято из стока

| Область | Что | Где |
|---|---|---|
| Память | нет `trusted_apps_region@ea000000` и `trusted_apps_ext_region@ed900000` (+116 МиБ Linux) | `cape-reserved-memory.dtsi` |
| Crash dump | `mem_dump_region` 48 МиБ и стоковая таблица из 97 записей | `cape-debug.dtsi` |
| MMRM | 5 корнеров, коэффициенты и 28 клиентов Cape | `mondrian-mmrm-overlay.dts` |
| Камера | `CAMERA_MACRO_IOVDD` (gpio-regulator на GPIO 7) | camera board overlay |
| Термо | `mdmss{0..3}-config{0,1}` типа `active` | `cape-thermal.dtsi` |
| Дисплей M11A | физический размер, команды инициализации и переключения 60/90/120 Гц | `mondrian-m11a-os3-panel-commands.dtsi` (генерируется) |
| Аудио | третичный интерфейс как TDM, ультразвук (UPD), UART-переключатель MBHC, маршруты | `mondrian-audio-board-overlay.dts` |
| ADSP/CDSP | прерывание `shutdown-ack` (smp2p 7), читает `qcom_sysmon.c` | `cape.dtsi` |
| Сенсоры | `qcom,fastrpc-slpi-sensors-pdr` вместо adsp (сенсоры на SLPI), читает `adsprpc.c` | `cape.dtsi` |
| GPU | `qcom,cx-level` для 13 уровней, читает `adreno.c` | `cape-gpu.dtsi` |
| QSEECOM | `qcom,uncached-heap`, читает `qcom_dt_parser.c` | `cape-dma-heaps.dtsi` |
| USB | U1/U2 разрешены (нет `snps,dis-u1/u2-entry-quirk`) | `cape-usb.dtsi` |
| USB3 PHY | стоковая последовательность QMP (PLL от CLKREF 38,4 МГц, подстройка RX) и часы `ref_clk` = `GCC_USB3_0_CLKREF_EN` | `cape-usb.dtsi` |

Последовательность USB3 PHY в стоке записана парами `<смещение значение>`
(формат нового драйвера), а наш `phy-msm-ssusb-qmp.c` читает тройки
`<смещение значение задержка>` с завершающим `0xffffffff`. Поэтому
значения стока перенесены в наш формат; скомпилированная
последовательность совпадает со стоковой регистр в регистр.

## Сознательно оставлено иначе, чем в стоке

| Свойство | Почему |
|---|---|
| прерывание `eusb2_rptr_reset_gpio_irq` у `eusb2_repeater@4f` | в стоке его нет, но наш `repeater-i2c-eusb2.c` без него завершает probe ошибкой — USB не заработает |
| `qcom,cam-res-mgr`: `qcom,shared-pinctrl-gpios` вместо `gpios-shared-pinctrl = <427 371 303 403>` | сток задаёт глобальные номера GPIO, верные только при базе TLMM 301; наша запись через phandle на те же пины 126/70/2/102 от порядка probe не зависит, пропатченный `cam_res_mgr.c` читает обе формы |
| `freq_limiter_irq` и сброс у `qcom,kgsl-3d0` | наш kgsl их не читает |
| `qcom,no-wake-svc` у `slpi_qrtr` | наш qrtr его не читает |
| термозоны `sdr0-pa`, `sdr1-pa` | наш `qmi_sensors` не знает этих датчиков; потребителей в стоке нет |
| свойства `mi,*` панели | наш драйвер дисплея их не читает; локальный HBM для FOD — `mondrian_fod.c` в ядре |

## Осталось сверить

- pinctrl: 46 узлов только в стоке и 54 только у нас — в основном разные
  имена одних и тех же состояний; нужна сверка по пинам и функциям, а не
  по именам;
- узлы TGU, алиас `i2c5`, отладочные регистры PCIe.

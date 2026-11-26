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
| USB | `GCC_USB3_0_CLKREF_EN` держит только PHY (у контроллера нет `xo`) | `cape-usb.dtsi` |
| PCIe | ревизия PHY 99: шаг SSC и дробная часть PLL (VCO 9998 МГц), настройка RX на каждой линии | `cape-pcie.dtsi` |
| PCIe0 | списки регистров PHY/PARF/DBI для дампа при сбое линка Wi-Fi | `cape-pcie.dtsi` |
| Coresight | триггеры SPMI `tgu@10b0f000`, `tgu@10b10000` (сток грузит `coresight-tgu.ko`) | `cape-coresight.dtsi` |
| I2C | алиас `i2c5` = `qupv3_se17_i2c`: та же нумерация динамических шин, что в стоке | `cape.dtsi` |
| Вибромотор | LRA mondrian: предел 1250 мВ и период 5882 мкс (170 Гц) вместо общих 2700 мВ / 196 Гц из `pm8350b.dtsi` | `cape-pmic-overlay.dtsi` |
| Кнопки | debounce громкости 32 мс | `xiaomi-sm8475-common.dtsi` |
| Камера | карта IOVA ICP: общая область на 50 МиБ больше, конец карты тот же | camera board overlay |
| Аудио | `qcom,tert-mi2s-gpios` указывает на пины TDM, а не на выключенные пины MI2S | `mondrian-audio-board-overlay.dts` |
| Аудио | WCD938x: TX-порт 1 в use case 0 на линии данных 2 SoundWire | `mondrian-audio-board-overlay.dts` |

Ссылка `qcom,tert-mi2s-gpios` исправляет ошибку: `msm_common.c` при старте
третичного интерфейса переключает эти пины и при неудаче завершает поток с
ошибкой, то есть динамик и наушник (AW882xx на TDM) не запустились бы.
Сборщик `build_mondrian_multimedia.py` теперь это проверяет.

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
| свойства `mi,*` панели, кроме тех, что читает `mondrian_fod*.c` | наш драйвер дисплея их не читает; все свойства, которые читает наш код FOD/LHBM, совпадают со стоком |
| пустой `gpio-reset` у `qcom,eeprom2` | наш `cam_sensor_util.c` считает пустое значение ошибкой разбора |
| `qcom,prime-mask`, `qcom,silver-mask` у UFS; `qcom,dll_lock_bist_fail_wa` у SDHCI | наше ядро их не читает |
| `qcom,cdc-dmic67-gpios` | наш `waipio.c` обслуживает только DMIC 0–5, пины DMIC67 выключены в обоих деревьях |
| `sound-name-prefix` вместо `qcom,swr-dmic-prefix` / `qcom,wsa-prefix` | версия драйвера: наш audio-kernel читает `qcom,*-prefix` |
| `qcom,cps_*`, `#cooling-cells` у WSA | WSA883x на mondrian нет |
| свойства других панелей (L1, L2S, L18, M16T) | на mondrian только M11A |

## pinctrl

Узлы состояний pinctrl у нас и в стоке называются по-разному (например,
`mondrian-active-rst0` и `cam_sensor_active_rst0`), поэтому сверка идёт по
потребителям: для каждого включённого узла и каждого его состояния
`pinctrl-N` сравнивается итоговая настройка каждого пина (функция, ток,
подтяжка, уровень). У всех 177 потребителей она совпадает со стоком.

## Как сравнивается

Скомпилированные деревья разбираются целиком. Ссылки phandle
разворачиваются в пути узлов, остальные значения сравниваются побайтно.
Если сырые значения отличаются, но совпадают после разворачивания,
отличие — только номер phandle.

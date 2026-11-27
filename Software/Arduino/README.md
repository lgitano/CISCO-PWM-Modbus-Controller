# Arduino Nano Firmware

Firmware for the **Arduino Nano (ATmega328P)** handling:
- **31 kHz Phase-Correct PWM** on Timer 1 (`D9` / `D10`) for both Buck-PWM fan channels
- **4-Channel 10 kΩ NTC** temperature acquisition (`A0`–`A3`) via Steinhart-Hart calculation
- **I²C Master communication (`Wire`)** with the Cisco AA23200 `ADM1041` controller (`CN940`, `A4`/`A5`)
- **Galvanically isolated Modbus RTU Slave** over hardware UART (`D0`/`D1`) + `DE/RE` (`D4`)
- **Isolated E-Stop monitoring** (`D5`) & open-drain tacho signal output (`D2`)

## Required Libraries

Install via the **Arduino Library Manager** (`Sketch -> Include Library -> Manage Libraries...`):

- **`Wire`** *(built-in Arduino I²C library)*
- **`ModbusRTUSlave`** *(by CMB27)*

## Board & Flashing Settings

- **Board:** `Arduino Nano`
- **Processor:** `ATmega328P` *(or `ATmega328P (Old Bootloader)` for clone boards)*
- **USB Note:** Disconnect the RS485 transceiver / jumper if flashing issues occur on `RX`/`TX` (`D0`/`D1`), though the `PC817` optocoupler (`U3`) is already decoupled so USB uploads normally work in-circuit.

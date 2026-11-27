# PyQt5 & LinuxCNC (QtDragon / QtVCP) Panels

Host-side graphical user interfaces for monitoring temperatures, PSU voltage/current, and controlling fan speeds & output voltage over **Modbus RTU (RS485)**.

---

## 1. Standalone PyQt5 Panel (`pyqt_modbus.py`)

Runs directly from the terminal without LinuxCNC installed (ideal for bench testing or lab PSU operation).

### Requirements
```bash
pip install PyQt5 pymodbus pyserial
```

### Usage
```bash
python3 pyqt_modbus.py
```
*(Select your USB-RS485 serial port, e.g. `/dev/ttyUSB0` on Linux or `COMx` on Windows, matching the Arduino's baud rate and Modbus Slave ID.)*

---

## 2. LinuxCNC / QtDragon Embedded Panel (`cisco_panel`)

Integrates directly into **LinuxCNC QtVCP / QtDragon** as a custom sub-panel.

### Installation
1. Copy both panel files into your machine's `qtvcp/panels` directory:
   ```text
   ~/linuxcnc/configs/<your_machine_config>/qtvcp/panels/cisco_panel.ui
   ~/linuxcnc/configs/<your_machine_config>/qtvcp/panels/cisco_panel_handler.py
   ```
2. Reference `cisco_panel` in your machine's `.ini` file under `[DISPLAY]` (using `EMBED_TAB_NAME` / `EMBED_TAB_COMMAND = qtvcp cisco_panel`, depending on your QtDragon layout).

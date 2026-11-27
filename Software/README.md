# Software & HMI Panels

Firmware for the **Arduino Nano** controller as well as **PyQt / QtVCP** user interfaces to communicate with the Cisco AA23200 controller over **Modbus RTU (RS485)** — either standalone from the command line or embedded directly into **LinuxCNC / QtDragon**.

## Directory Structure

```text
Software/
├── Arduino/    # Arduino Nano firmware (31 kHz Buck-PWM, NTCs, ADM1041 I²C, Modbus RTU)
└── qqt/        # Standalone PyQt5 GUI & LinuxCNC QtVCP panel files for QtDragon
```

## Quick Overview

1. **Microcontroller (`Arduino/`):** Flash the firmware onto an **Arduino Nano (ATmega328P)** using the Arduino IDE or PlatformIO.
2. **Host Interface (`qqt/`):**
   - Run `pyqt_modbus.py` standalone on any Linux/Windows/macOS machine with a USB-to-RS485 adapter.
   - Or embed `cisco_panel.ui` + `cisco_panel_handler.py` as a custom tab/panel inside **LinuxCNC (QtDragon / QtVCP)**.

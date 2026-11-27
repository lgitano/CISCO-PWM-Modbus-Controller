import sys
import minimalmodbus
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QDoubleSpinBox, QSlider, QCheckBox, QGroupBox, QTextEdit
)
from PyQt5.QtCore import Qt, QTimer
from datetime import datetime

PORT = '/dev/serial/by-id/usb-1a86_USB2.0-Ser_-if00-port0'
SLAVE_ID = 1
BAUDRATE = 19200

QTDRAGON_STYLE = """
QWidget { background-color: #1e2024; color: #e0e4ec; font-family: 'Segoe UI', 'Ubuntu', sans-serif; font-size: 14px; }
QGroupBox {
    border: 1px solid #3a3f4b;
    border-radius: 5px;
    margin-top: 4px;
    padding-top: 18px;
    padding-bottom: 4px;
    font-weight: bold;
    color: #5bc0de;
}
QGroupBox::title {
    subcontrol-origin: border;
    subcontrol-position: top left;
    left: 8px;
    top: 3px;
    padding: 0px 4px;
    background-color: transparent;
}
QLabel#BigValue { font-size: 28px; font-weight: bold; color: #4cd964; background-color: #141619; border: 1px solid #2e323b; border-radius: 4px; padding: 8px 12px; }
QLabel#StatusBadge { font-weight: bold; padding: 6px 12px; border-radius: 4px; background-color: #2c303a; }
QPushButton { background-color: #2d323e; border: 1px solid #4a5162; border-radius: 4px; padding: 7px 14px; font-weight: bold; }
QPushButton:hover { background-color: #3a4150; border-color: #5bc0de; }
QDoubleSpinBox { background-color: #141619; border: 1px solid #4a5162; border-radius: 4px; padding: 6px; font-size: 16px; font-weight: bold; color: #ffcc00; }
"""

def voltage_to_trim(target_volt: float) -> int:
    if target_volt <= 41.10: return 0x99
    if target_volt >= 50.90: return 0x02
    if target_volt < 41.70:
        steps = int((41.70 - target_volt) / 0.0122 + 0.5)
        return min(0x99, 0x68 + steps)
    steps = int((target_volt - 41.70) / 0.0902 + 0.5)
    trim = 0x68 - steps
    return 0x02 if trim < 0x02 else trim

def decode_adm1041(s1: int, s2: int, s3: int, status_word: int) -> str:
    if status_word & (1 << 10):
        return "Netzteil im Standby (I2C-Controller ADM1041 schläft / keine Rückmeldung)."
    
    meldungen = []
    if status_word & (1 << 1): meldungen.append("KRITISCH: Übertemperatur >= 75 °C")
    if s1 & (1 << 5): meldungen.append("FEHLER (S1.5): Überstromschutz (OCP)")
    if s1 & (1 << 4): meldungen.append("FEHLER (S1.4): Überspannungsschutz (OVP)")
    if s1 & (1 << 3): meldungen.append("FEHLER (S1.3): Unterspannungsschutz (UVP)")
    if not (s2 & (1 << 6)): meldungen.append("WARNUNG (S2.6): OVP-Warnschwelle")
    if not (s2 & (1 << 5)): meldungen.append("WARNUNG (S2.5): UVP-Warnschwelle")
    if not (s2 & (1 << 4)): meldungen.append("WARNUNG (S2.4): Rückstrom (Reverse Current)")
    if not (s2 & (1 << 2)): meldungen.append("WARNUNG (S2.2): Interne Übertemperatur (OTP)")
    if not (s3 & (1 << 6)): meldungen.append("WARNUNG (S3.6): Lüfter- / Tacho-Fehler")

    if not meldungen:
        return "Alle ADM1041 Schutz- & Überwachungskreise melden: OK."
    return " | ".join(meldungen)
class CiscoQtDragonPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("QtDragon SYSTEM | Cisco AA23200 Smart-PSU")
        self.resize(780, 680)
        self.setStyleSheet(QTDRAGON_STYLE)

        self.psu = None
        self.psu_requested_on = False
        self.last_log_msg = ""
        self.init_modbus()
        self.init_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_modbus)
        self.timer.start(500)
        self.fan_timer = QTimer(self)
        self.fan_timer.setSingleShot(True)
        self.fan_timer.timeout.connect(self.write_fan_speed)
        self.tacho_timer = QTimer(self)
        self.tacho_timer.setSingleShot(True)
        self.tacho_timer.timeout.connect(self.sync_holding_regs)

    def init_modbus(self):
        try:
            self.psu = minimalmodbus.Instrument(PORT, SLAVE_ID)
            self.psu.clear_buffers_before_each_transaction = True
            self.psu.close_port_after_each_call = False
            self.psu.serial.baudrate = BAUDRATE
            self.psu.serial.timeout = 0.25
            self.psu.handle_local_echo = False
        except Exception as e:
            print(f"Modbus Init Fehler: {e}")

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        # 1. Kopfzeile mit klickbarem 150-kHz-Hauptschalter
        header = QHBoxLayout()
        self.lbl_conn = QLabel("BUS: VERBINDE...")
        self.lbl_conn.setObjectName("StatusBadge")

        self.btn_psu_toggle = QPushButton("150 kHz TACHO-SIM: AUS (Klick = EIN)")
        self.btn_psu_toggle.setCursor(Qt.PointingHandCursor)
        self.btn_psu_toggle.setStyleSheet(
            "background-color: #4a3b18; color: #ffcc00; border: 1px solid #ffcc00; padding: 6px 14px;"
        )
        self.btn_psu_toggle.clicked.connect(self.toggle_psu_power)

        self.lbl_err = QLabel("STATUS: WARTE...")
        self.lbl_err.setObjectName("StatusBadge")

        header.addWidget(self.lbl_conn)
        header.addWidget(self.btn_psu_toggle, stretch=1)
        header.addWidget(self.lbl_err)
        main_layout.addLayout(header)
        body_split = QHBoxLayout()
        body_split.setSpacing(8)
        left_col = QVBoxLayout()
        left_col.setSpacing(4)
        right_col = QVBoxLayout()
        right_col.setSpacing(4)
        body_split.addLayout(left_col, 1)
        body_split.addLayout(right_col, 1)
        main_layout.addLayout(body_split)

        # 2. Hauptwerte
        power_group = QGroupBox("AUSGANGSLEISTUNG (48V DC BUS)")
        power_grid = QGridLayout(power_group)

        self.lbl_volt = QLabel("00.00 V")
        self.lbl_volt.setObjectName("BigValue")
        self.lbl_volt.setAlignment(Qt.AlignCenter)

        self.lbl_curr = QLabel("00.00 A")
        self.lbl_curr.setObjectName("BigValue")
        self.lbl_curr.setAlignment(Qt.AlignCenter)

        self.lbl_watt = QLabel("0 W")
        self.lbl_watt.setObjectName("BigValue")
        self.lbl_watt.setAlignment(Qt.AlignCenter)

        power_grid.addWidget(QLabel("SPANNUNG"), 0, 0, Qt.AlignCenter)
        power_grid.addWidget(QLabel("STROM"), 0, 1, Qt.AlignCenter)
        power_grid.addWidget(QLabel("LEISTUNG"), 0, 2, Qt.AlignCenter)
        power_grid.addWidget(self.lbl_volt, 1, 0)
        power_grid.addWidget(self.lbl_curr, 1, 1)
        power_grid.addWidget(self.lbl_watt, 1, 2)
        self.lbl_rpm = QLabel("---- RPM")
        self.lbl_rpm.setObjectName("BigValue")
        power_grid.addWidget(QLabel("LÜFTERDREHZAHL:"), 0, 3)
        power_grid.addWidget(self.lbl_rpm, 1, 3)
        left_col.addWidget(power_group)

        # 3. Thermik & Kuehlung
        temp_group = QGroupBox("THERMIK && KÜHLUNG")
        temp_grid = QGridLayout(temp_group)
        self.temp_labels = []
        names = ["Chip (ADM1041)", "NTC 1 (A0)", "NTC 2 (A1)", "NTC 3 (A2)", "NTC 4 (A3)", "Lüfter PWM"]
        for i, name in enumerate(names):
            lbl_name = QLabel(name)
            lbl_val = QLabel("--.- °C" if i < 5 else "-- %")
            lbl_val.setStyleSheet("font-weight: bold; color: #5bc0de; font-size: 15px;")
            temp_grid.addWidget(lbl_name, i // 3, (i % 3) * 2)
            temp_grid.addWidget(lbl_val, i // 3, (i % 3) * 2 + 1)
            self.temp_labels.append(lbl_val)
        left_col.addWidget(temp_group)

        # 4. Steuerung
        ctrl_group = QGroupBox("STEUERUNG (HOLDING REGISTER)")
        ctrl_grid = QGridLayout(ctrl_group)

        ctrl_grid.addWidget(QLabel("Zielspannung (V):"), 0, 0)
        self.spin_volt = QDoubleSpinBox()
        self.spin_volt.setRange(41.10, 50.90)
        self.spin_volt.setSingleStep(0.10)
        self.spin_volt.setValue(48.04)
        ctrl_grid.addWidget(self.spin_volt, 0, 1)

        btn_set_volt = QPushButton("Spannung setzen")
        btn_set_volt.clicked.connect(self.write_voltage)
        ctrl_grid.addWidget(btn_set_volt, 0, 2)

        self.chk_fan_man = QCheckBox("Lüfter Manuell")
        self.chk_fan_man.stateChanged.connect(self.write_fan_mode)
        ctrl_grid.addWidget(self.chk_fan_man, 1, 0)

        self.slider_fan = QSlider(Qt.Horizontal)
        self.slider_fan.setRange(10, 100)
        self.slider_fan.setValue(15)
        self.lbl_slider_val = QLabel("15 %")
        self.slider_fan.valueChanged.connect(self.on_slider_moved)
        

        ctrl_grid.addWidget(self.slider_fan, 1, 1)
        ctrl_grid.addWidget(self.lbl_slider_val, 1, 2)

        # ctrl_grid.addWidget(QLabel("Tacho-Fake (Hz):"), 2, 0)
        # self.slider_tacho = QSlider(Qt.Horizontal)
        # self.slider_tacho.setRange(200, 15000)
        # self.slider_tacho.setSingleStep(50)
        # self.slider_tacho.setPageStep(250)
        # self.slider_tacho.setValue(1500)
        # self.lbl_tacho_val = QLabel("1500 Hz")
        # self.slider_tacho.valueChanged.connect(self.on_tacho_moved)
        # ctrl_grid.addWidget(self.slider_tacho, 2, 1)
        # ctrl_grid.addWidget(self.lbl_tacho_val, 2, 2)

        left_col.addWidget(ctrl_group)

        # 5. ADM1041 Klartext-Diagnose
        diag_group = QGroupBox("ADM1041 KLARTEXT-DIAGNOSE (I2C 0x57)")
        diag_layout = QVBoxLayout(diag_group)
        self.lbl_diag_hex = QLabel("Register: S1=0x00 | S2=0x00 | S3=0x00 | StatusWord=0x0000")
        self.lbl_diag_hex.setStyleSheet("font-family: monospace; color: #8c96a6;")
        self.txt_diag_log = QTextEdit(); self.txt_diag_log.setReadOnly(True); self.txt_diag_log.setMinimumHeight(160); self.txt_diag_log.setStyleSheet("background-color: #141619; border: 1px solid #2e323b; font-family: monospace; font-size: 13px; color: #e0e4ec;")
        
        
        diag_layout.addWidget(self.lbl_diag_hex)
        diag_layout.addWidget(self.txt_diag_log)
        right_col.addWidget(diag_group)

    def sync_holding_regs(self):
        if not self.psu: return
        trim = voltage_to_trim(self.spin_volt.value())
        mode = 1 if self.chk_fan_man.isChecked() else 0
        speed = self.slider_fan.value()
        pson = 1 if self.psu_requested_on else 0
        tacho_hz = 1500  # self.slider_tacho.value()
        try:
            self.psu.write_registers(0, [trim, mode, speed, pson, tacho_hz])
        except Exception as e:
            print(f"Modbus Write Fehler: {e}")

    def sync_holding_regs(self):
        if not self.psu: return
        trim = voltage_to_trim(self.spin_volt.value())
        mode = 1 if self.chk_fan_man.isChecked() else 0
        speed = self.slider_fan.value()
        pson = 1 if self.psu_requested_on else 0
        tacho_hz = 1500  # self.slider_tacho.value()
        try:
            self.psu.write_registers(0, [trim, mode, speed, pson, tacho_hz])
        except Exception as e:
            print(f"Modbus Write Fehler: {e}")

    def toggle_psu_power(self):
        self.psu_requested_on = not self.psu_requested_on
        self.sync_holding_regs()

    def write_voltage(self):
        self.sync_holding_regs()

    def write_fan_mode(self, state):
        self.sync_holding_regs()

    def on_tacho_moved(self, v):
        self.lbl_tacho_val.setText(f"{v} Hz")
        self.tacho_timer.start(150)

    def on_slider_moved(self, v):
        self.lbl_slider_val.setText(f"{v} %")
        self.fan_timer.start(150)

    def write_fan_speed(self):
        if not self.chk_fan_man.isChecked():
            self.chk_fan_man.blockSignals(True)
            self.chk_fan_man.setChecked(True)
            self.chk_fan_man.blockSignals(False)
        self.sync_holding_regs()

    def poll_modbus(self):
        if not self.psu:
            self.init_modbus()
            return
        try:
            regs = self.psu.read_registers(0, 13, functioncode=4)
            self.lbl_conn.setText("BUS: ONLINE")
            self.lbl_conn.setStyleSheet(
                "background-color: #1e4620; color: #4cd964; font-weight: bold; padding: 6px 12px; border-radius: 4px;"
            )

            status = regs[0]
            online = bool(status & 1)
            self.psu_requested_on = online

            if online:
                self.btn_psu_toggle.setText("150 kHz TACHO-SIM: AKTIV – Klick = AUS")
                self.btn_psu_toggle.setStyleSheet(
                    "background-color: #1e4620; color: #4cd964; border: 1px solid #4cd964; padding: 6px 14px;"
                )
            else:
                self.btn_psu_toggle.setText("150 kHz TACHO-SIM: AUS – Klick = EIN")
                self.btn_psu_toggle.setStyleSheet(
                    "background-color: #4a3b18; color: #ffcc00; border: 1px solid #ffcc00; padding: 6px 14px;"
                )

            real_alarms = (status >> 1) & 0x01FF
            if real_alarms:
                self.lbl_err.setText("ALARM / WARNUNG!")
                self.lbl_err.setStyleSheet(
                    "background-color: #5c1d1d; color: #ff5252; font-weight: bold; padding: 6px 12px; border-radius: 4px;"
                )
            elif status & (1 << 10):
                self.lbl_err.setText("I2C: STANDBY")
                self.lbl_err.setStyleSheet(
                    "background-color: #2c303a; color: #5bc0de; font-weight: bold; padding: 6px 12px; border-radius: 4px;"
                )
            else:
                self.lbl_err.setText("SCHUTZ: OK")
                self.lbl_err.setStyleSheet(
                    "background-color: #1e4620; color: #4cd964; font-weight: bold; padding: 6px 12px; border-radius: 4px;"
                )

            self.lbl_volt.setText(f"{regs[1] / 100.0:.2f} V")
            self.lbl_curr.setText(f"{regs[2] / 100.0:.2f} A")
            self.lbl_watt.setText(f"{regs[3]} W")

            # Temperaturen: Chip + NTC 1..4 + Lüfter %
            temps = [regs[4], regs[5], regs[6], regs[7], regs[8]]
            for i, t_raw in enumerate(temps):
                self.temp_labels[i].setText(f"{t_raw / 10.0:.1f} °C")
            self.temp_labels[5].setText(f"{regs[9]} %")
            try:
                rpm_regs = self.psu.read_registers(13, 1, functioncode=4)
                rpm_val = rpm_regs[0]
            except Exception:
                rpm_val = int(regs[9] * 180) if regs[9] > 0 else 0
            self.lbl_rpm.setText(f"{rpm_val} RPM")

            # Klartext-Diagnose
            s1, s2, s3 = regs[10], regs[11], regs[12]
            self.lbl_diag_hex.setText(
                f"Register: S1=0x{s1:02X} | S2=0x{s2:02X} | S3=0x{s3:02X} | StatusWord=0x{status:04X}"
            )
            msg = decode_adm1041(s1, s2, s3, status)
            if msg != self.last_log_msg:
                self.txt_diag_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
                self.last_log_msg = msg

        except Exception as e:
            self.lbl_conn.setText("BUS: OFFLINE")
            self.lbl_conn.setStyleSheet(
                "background-color: #5c1d1d; color: #ff5252; font-weight: bold; padding: 6px 12px; border-radius: 4px;"
            )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = CiscoQtDragonPanel()
    win.show()
    sys.exit(app.exec_())



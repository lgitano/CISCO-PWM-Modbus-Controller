#include <Wire.h>
#include <ModbusRTUSlave.h>

// --- Pin-Belegung ---
const uint8_t PIN_ESTOP_OK    = 5;   // D5 -> R6 (300R) -> U4 (PC817)
const uint8_t PIN_DE_RE       = 4;   // MAX485 DE + RE (D4)
const uint8_t PIN_PSON_150KHZ = 3;   // 150 kHz Tacho-Signal (D3, Timer 2)
const uint8_t PIN_FAN1        = 9;   // IRLZ44N Kanal 1: Cisco Magic Lüfter (D9)
const uint8_t PIN_FAN2        = 10;  // IRLZ44N Kanal 2: Scythe / Zusatzlüfter (D10)
const uint8_t NTC_PINS[0 + 4] = {A0, A1, A2, A3};

// --- Modbus RTU Konfiguration ---
const uint8_t  SLAVE_ID = 1;
const uint32_t BAUDRATE = 19200;

ModbusRTUSlave modbus(Serial, PIN_DE_RE);
uint16_t inputRegs[0 + 13];   // FC04: 0..12
uint16_t holdingRegs[0 + 5];  // FC03/06/16: 0..3

// --- Cisco AA23200 / ADM1041 I2C Konfiguration (0x57) ---
const uint8_t CISCO_I2C_ADDR = 0x57;
uint8_t aktuellerTrimWert    = 0x1F; // Start: 0x1F = 47,80 V
uint16_t lastAppliedTrim     = 0xFFFF;
unsigned long lastSample     = 0;

// --- NTC & Lüfter Parameter ---
const float NTC_R25        = 10000.0;
const float NTC_BETA       = 3950.0;
const float SERIES_R       = 10000.0;

const uint8_t FAN1_MIN_PCT = 15;
const uint8_t FAN2_MIN_PCT = 15;
const float TEMP_START     = 42.0;
const float TEMP_FULL      = 60.0;

float readNTC(uint8_t idx) {
  long sum = 0;
  for (int s = 0; s < 8; s++) {
    sum += analogRead(NTC_PINS[idx]);
    delayMicroseconds(100);
  }
  float adc = sum / 8.0;
  if (adc <= 40.0 || adc >= 985.0) return 0.0;
  float r = SERIES_R / ((1023.0 / adc) - 1.0);
  float steinhart = log(r / NTC_R25) / NTC_BETA + (1.0 / 298.15);
  float tempC = (1.0 / steinhart) - 273.15;
  return (tempC > -10.0 && tempC < 150.0) ? tempC : 0.0;
}



void writeAdmReg(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(CISCO_I2C_ADDR);
  Wire.write(reg);
  Wire.write(value);
  Wire.endTransmission();
  delay(5);
}

uint8_t readAdmReg(uint8_t reg) {
  Wire.beginTransmission(CISCO_I2C_ADDR);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return 0;
  Wire.requestFrom((uint8_t)CISCO_I2C_ADDR, (uint8_t)1);
  if (Wire.available() > 0) return Wire.read();
  return 0;
}

bool isNetzteilOnline() {
  for (int i = 0; i < 3; i++) {
    Wire.beginTransmission(CISCO_I2C_ADDR);
    if (Wire.endTransmission() == 0) return true;
    delayMicroseconds(500);
  }
  return false;
}

void applyVoltageTrim(uint8_t targetValue) {
  if (!isNetzteilOnline()) return;
  writeAdmReg(0x07, 0x00);
  writeAdmReg(0x08, 0xC0);
  uint8_t config5 = readAdmReg(0x11);
  config5 |= 0x10;
  config5 &= ~0x02;
  writeAdmReg(0x11, config5);
  writeAdmReg(0x19, targetValue);
  aktuellerTrimWert = targetValue;
}

void updateTachoFreq(bool enable, uint16_t freqHz) {
  static uint16_t lastFreq = 0;
  static bool lastEn = false;
  if (!enable) {
    OCR2B = 0;
    lastEn = false;
    return;
  }
  freqHz = constrain(freqHz, 200, 20000);
  if (!lastEn || freqHz != lastFreq) {
    // Prescaler 64 -> 16 MHz / 64 = 250.000 Hz Basistakt (deckt 980 Hz .. 20 kHz ab)
    // Prescaler 256 -> 16 MHz / 256 = 62.500 Hz Basistakt (deckt 245 Hz .. 979 Hz ab)
    if (freqHz >= 980) {
      TCCR2B = _BV(WGM22) | _BV(CS22); // Prescaler 64
      uint8_t top = (uint8_t)(250000UL / freqHz) - 1;
      OCR2A = top;
      OCR2B = top / 2;
    } else {
      TCCR2B = _BV(WGM22) | _BV(CS22) | _BV(CS21); // Prescaler 256
      uint8_t top = (uint8_t)(62500UL / freqHz) - 1;
      OCR2A = top;
      OCR2B = top / 2;
    }
    lastFreq = freqHz;
    lastEn = true;
  }
}


void setup() {
  pinMode(PIN_ESTOP_OK, OUTPUT);
  digitalWrite(PIN_ESTOP_OK, LOW); // Startet sicher, erst nach Boot-Check HIGH

  pinMode(PIN_FAN1, OUTPUT);
  pinMode(PIN_FAN2, OUTPUT);
  pinMode(PIN_PSON_150KHZ, OUTPUT);

  TCCR1B = (TCCR1B & 0b11111000) | 0x01;

  TCCR2A = _BV(COM2B1) | _BV(WGM21) | _BV(WGM20);
  TCCR2B = _BV(WGM22) | _BV(CS22) | _BV(CS21); // Prescaler 256  
  //OCR2A  = 106;
  OCR2A  = 62; // 16 MHz / (256 * 125) = 500 Hz
  OCR2B  = 31;

  analogWrite(PIN_FAN1, 255);
  analogWrite(PIN_FAN2, 255);
  delay(1200);
  analogWrite(PIN_FAN1, map(FAN1_MIN_PCT, 0, 100, 0, 255));
  analogWrite(PIN_FAN2, map(FAN2_MIN_PCT, 0, 100, 0, 255));

  holdingRegs[0 + 0] = 0x1F;
  holdingRegs[0 + 1] = 0;
  holdingRegs[0 + 2] = 20;
  holdingRegs[0 + 3] = 0;
  holdingRegs[0 + 4] = 1500; // Start: 1500 Hz Tacho-Fake
  
  Wire.begin();
  Wire.setClock(100000);
  Wire.setWireTimeout(3000, true);

  Serial.begin(BAUDRATE);
  modbus.configureInputRegisters(inputRegs, 13);
  modbus.configureHoldingRegisters(holdingRegs, 5);
  modbus.begin(SLAVE_ID, BAUDRATE);
}
void loop() {
  modbus.poll();

  // 150-kHz-Tacho-Signal sofort schalten (ohne 250-ms-Verzögerung)
  static float lastMaxTemp = 0.0;
  bool overTempNow = (lastMaxTemp >= 75.0);
  bool psuOnNow = (holdingRegs[0 + 3] == 1) && !overTempNow;
  updateTachoFreq(psuOnNow, holdingRegs[0 + 4]);

  if (millis() - lastSample >= 250) {
    lastSample = millis();

    // 1. NTC-Temperaturen einlesen (0,1 °C)
    float maxTemp = 0.0;
    for (int i = 0; i < 4; i++) {
      float t = readNTC(i);
      inputRegs[5 + i] = (t > 0.0) ? (uint16_t)(t * 10.0) : 0;
      if (t > maxTemp) maxTemp = t;
    }

    // 2. Cisco ADM1041 Telemetrie & Fehler-Register (0x57)
    bool online = isNetzteilOnline();
    uint16_t statusWord = 0;

    if (online) {
      uint8_t targetTrim = constrain((int)holdingRegs[0 + 0], 0x02, 0x99);
      if (targetTrim != lastAppliedTrim) {
        int diff = (int)targetTrim - (int)lastAppliedTrim;
        if (lastAppliedTrim == 0xFFFF) {
          lastAppliedTrim = targetTrim;
        } else if (abs(diff) > 4) {
          lastAppliedTrim += (diff > 0) ? 4 : -4;
        } else {
          lastAppliedTrim = targetTrim;
        }
        applyVoltageTrim((uint8_t)lastAppliedTrim);
      }

      uint8_t stromADC = readAdmReg(0x15);

      uint8_t rawTemp = readAdmReg(0x18);
      static uint8_t validTempInt = 35;
      if (rawTemp > 0 && rawTemp < 110 && abs((int)rawTemp - (int)validTempInt) < 15) {
        validTempInt = rawTemp;
      }
      uint8_t tempInt = validTempInt;

      uint8_t s1       = readAdmReg(0x00);
      uint8_t s2       = readAdmReg(0x01);
      uint8_t s3       = readAdmReg(0x02);

      if (s2 == 0x00) return;

      float volt = 0.0;
      if (aktuellerTrimWert > 0x68) {
        volt = 41.70 - ((aktuellerTrimWert - 0x68) * 0.0122);
      } else {
        volt = 41.70 + ((0x68 - aktuellerTrimWert) * 0.0902);
      }


      float ampere = (stromADC > 73) ? (stromADC - 73) * 0.35 : 0.0;
      // ... Rest von loop() bleibt unverändert


      inputRegs[0 + 1]  = (uint16_t)(volt * 100.0);
      inputRegs[0 + 2]  = (uint16_t)(ampere * 100.0);
      inputRegs[0 + 3]  = (uint16_t)(volt * ampere);
      inputRegs[0 + 4]  = (uint16_t)tempInt * 10;
      inputRegs[0 + 10] = s1;
      inputRegs[0 + 11] = s2;
      inputRegs[0 + 12] = s3;

      if ((float)tempInt > maxTemp) maxTemp = (float)tempInt;

      if (s1 & (1 << 5))    statusWord |= (1 << 2);  // OCP
      if (s1 & (1 << 4))    statusWord |= (1 << 3);  // OVP
      if (s1 & (1 << 3))    statusWord |= (1 << 4);  // UVP
      if (!(s2 & (1 << 6))) statusWord |= (1 << 5);  // OVP-Warnung
      if (!(s2 & (1 << 5))) statusWord |= (1 << 6);  // UVP-Warnung
      if (!(s2 & (1 << 4))) statusWord |= (1 << 7);  // Reverse Current
      if (!(s2 & (1 << 2))) statusWord |= (1 << 8);  // OTP intern Warnung
      if (!(s3 & (1 << 6))) statusWord |= (1 << 9);  // Lüfter / Tacho Fehler
    } else {
      inputRegs[0 + 1]  = 0;
      inputRegs[0 + 2]  = 0;
      inputRegs[0 + 3]  = 0;
      inputRegs[0 + 4]  = 0;
      inputRegs[0 + 10] = 0;
      inputRegs[0 + 11] = 0;
      inputRegs[0 + 12] = 0;
      lastAppliedTrim = 0xFFFF;
      statusWord |= (1 << 10); // Bit 10: Cisco Standby / schläft
    }

    // 3. Übertemperatur-Schutz (fest 75,0 °C) & StatusWord Bit 0
    static float smoothTemp = 25.0;
    smoothTemp = (smoothTemp * 0.85) + (maxTemp * 0.15);
    maxTemp = smoothTemp;
    lastMaxTemp = maxTemp;

    bool overTemp = (maxTemp >= 75.0);
    if (overTemp) statusWord |= (1 << 1);

    bool psuOn = (holdingRegs[0 + 3] == 1) && !overTemp;
    if (psuOn) statusWord |= (1 << 0);

    inputRegs[0 + 0] = statusWord;

// E-Stop nur freigeben (HIGH), wenn keine Übertemperatur und kein kritischer Fehler vorliegt
    bool systemHealthy = !overTemp && !(statusWord & ((1 << 2) | (1 << 3) | (1 << 4)));
    digitalWrite(PIN_ESTOP_OK, systemHealthy ? HIGH : LOW);

 //   // 4. Lüfter-Regelung (Reg 1 = Modus, Reg 2 = Speed)
 //   uint8_t fan1Pct = FAN1_MIN_PCT;
 //   uint8_t fan2Pct = FAN2_MIN_PCT;
 //
 //   if (holdingRegs[0 + 1] == 1) {
 //     fan1Pct = constrain(holdingRegs[0 + 2], 0, 100);
 //     fan2Pct = fan1Pct;
 //   } else if (maxTemp > TEMP_START) {
 //     float ratio = constrain((maxTemp - TEMP_START) / (TEMP_FULL - TEMP_START), 0.0, 1.0);
 //     fan1Pct = FAN1_MIN_PCT + (uint8_t)(ratio * (100 - FAN1_MIN_PCT));
 //     fan2Pct = FAN2_MIN_PCT + (uint8_t)(ratio * (100 - FAN2_MIN_PCT));
 //   }
 //   inputRegs[0 + 9] = fan1Pct;
 //   analogWrite(PIN_FAN1, map(fan1Pct, 0, 100, 0, 255));
 //   analogWrite(PIN_FAN2, map(fan2Pct, 0, 100, 0, 255));
 // }
     // 4. Lüfter-Regelung mit thermischem Sicherheits-Override
    uint8_t fan1Pct, fan2Pct;
    uint8_t auto1 = FAN1_MIN_PCT;
    uint8_t auto2 = FAN2_MIN_PCT;

    if (maxTemp > TEMP_START) {
      float ratio = constrain((maxTemp - TEMP_START) / (TEMP_FULL - TEMP_START), 0.0, 1.0);
      auto1 = FAN1_MIN_PCT + (uint8_t)(ratio * (100 - FAN1_MIN_PCT));
      auto2 = FAN2_MIN_PCT + (uint8_t)(ratio * (100 - FAN2_MIN_PCT));
    }

    if (holdingRegs[0 + 1] == 1) {
      uint8_t manPct = constrain(holdingRegs[0 + 2], 0, 100);
      fan1Pct = max(manPct, auto1); // Darf nie langsamer drehen, als die Temperatur erfordert!
      fan2Pct = max(manPct, auto2);
    } else {
      fan1Pct = auto1;
      fan2Pct = auto2;
    }

    if (maxTemp >= 65.0) { // Sicherheits-Vollgas vor der 75-°C-Notabschaltung
      fan1Pct = 100;
      fan2Pct = 100;
    }
    inputRegs[0 + 9] = fan1Pct;
    analogWrite(PIN_FAN1, map(fan1Pct, 0, 100, 0, 255));
    analogWrite(PIN_FAN2, map(fan2Pct, 0, 100, 0, 255));
  }
}

/* 
  PySatTrack - Hardware Controller
  Handles GNSS (GPS) Data and MPU6050 IMU Orientation.
  Communication: USB Serial (115200 baud)
*/

#include <Wire.h>
#include <TinyGPSPlus.h>
#include <LiquidCrystal_I2C.h>
#include <EEPROM.h>

// Initialize GPS and LCD
TinyGPSPlus gps;
LiquidCrystal_I2C lcd(0x27, 16, 2);

// MPU6050 Constants
const uint8_t MPU_ADDR = 0x68;
float gyroXoffset = 0.0, gyroYoffset = 0.0, gyroZoffset = 0.0;
float pitch = 0.0, roll = 0.0;

// Timing
unsigned long lastTelemetry = 0;
const int INTERVAL = 500; // 500ms telemetry rate

void setup() {
  Serial.begin(115200);   // Connection to Python
  Serial1.begin(9600);    // Connection to GPS Module (SIM7600)
  
  Wire.begin();
  lcd.init();
  lcd.backlight();
  
  // Initialize MPU6050
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x6B); // Power management register
  Wire.write(0);    // Wake up
  Wire.endTransmission(true);

  lcd.setCursor(0,0);
  lcd.print("PySatTrack HW");
  lcd.setCursor(0,1);
  lcd.print("Initializing...");
  delay(2000);
}

void loop() {
  // 1. Process GPS Data
  while (Serial1.available()) {
    gps.encode(Serial1.read());
  }

  // 2. Read IMU Data
  readIMU();

  // 3. Send Telemetry to Python
  if (millis() - lastTelemetry > INTERVAL) {
    sendTelemetry();
    updateLCD();
    lastTelemetry = millis();
  }

  // 4. Handle Commands from Python
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    processCommand(cmd);
  }
}

void readIMU() {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x3B);
  Wire.endTransmission(false);
  Wire.requestFrom(MPU_ADDR, 14, true);

  // Read Accelerometer and Gyro (simplified for this module)
  int16_t ax = (Wire.read() << 8) | Wire.read();
  int16_t ay = (Wire.read() << 8) | Wire.read();
  int16_t az = (Wire.read() << 8) | Wire.read();
  
  // Calculate basic pitch/roll
  pitch = atan2(ay, sqrt(pow(ax, 2) + pow(az, 2))) * 180 / PI;
  roll = atan2(-ax, az) * 180 / PI;
}

void sendTelemetry() {
  // Format as JSON for easy parsing in Python if needed, 
  // or keep as comma-separated for simple UART.
  Serial.print("GPS_LOCK:"); Serial.print(gps.location.isValid());
  Serial.print(",LAT:"); Serial.print(gps.location.lat(), 6);
  Serial.print(",LNG:"); Serial.print(gps.location.lng(), 6);
  Serial.print(",PITCH:"); Serial.print(pitch, 2);
  Serial.print(",ROLL:"); Serial.println(roll, 2);
}

void updateLCD() {
  lcd.clear();
  if (gps.location.isValid()) {
    lcd.setCursor(0,0);
    lcd.print("LAT: "); lcd.print(gps.location.lat(), 4);
    lcd.setCursor(0,1);
    lcd.print("LNG: "); lcd.print(gps.location.lng(), 4);
  } else {
    lcd.setCursor(0,0);
    lcd.print("Searching GPS...");
    lcd.setCursor(0,1);
    lcd.print("Sats: "); lcd.print(gps.satellites.value());
  }
}

void processCommand(String cmd) {
  // Example command from Python: "LCD:Hello|World"
  if (cmd.startsWith("LCD:")) {
    int split = cmd.indexOf('|');
    lcd.clear();
    lcd.setCursor(0,0);
    lcd.print(cmd.substring(4, split));
    if (split != -1) {
      lcd.setCursor(0,1);
      lcd.print(cmd.substring(split + 1));
    }
  }
}
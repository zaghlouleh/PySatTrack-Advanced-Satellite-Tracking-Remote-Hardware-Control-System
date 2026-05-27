/*
  ESP32 Dual RF Switch Controller (Version 3.0 - DUAL MODE CONTROL)
  ------------------------------------------------------------------
  This firmware provides THREE modes of operation for controlling two synchronized
  HMC253 SP8T switches, with a clear priority system.

  PRIORITY:
  1. AUTOMATED GPIO MODE (Highest Priority):
     - Listens for a 3-bit binary code on GPIO pins from a Raspberry Pi.
     - When the RPI_OVERRIDE pin is pulled LOW, this mode takes exclusive control,
       locking out both Serial and Wi-Fi commands.

  2. AUTOMATED SERIAL MODE (Medium Priority):
     - Listens for commands via the USB Serial port (e.g., "SET:5\n").
     - This allows a PC running the main Python application to control the switch.
     - This mode is active only when GPIO override is NOT active.

  3. MANUAL WI-FI MODE (Lowest Priority):
     - Creates a Wi-Fi AP for manual control via a web browser.
     - This mode is active only when GPIO override is NOT active and no
       valid Serial command has been recently received.

  Hardware Connections:
  - ESP32 GPIO 18 -> S0 (Control Pin 0) on BOTH switches (OUTPUT)
  - ESP32 GPIO 19 -> S1 (Control Pin 1) on BOTH switches (OUTPUT)
  - ESP32 GPIO 21 -> S2 (Control Pin 2) on BOTH switches (OUTPUT)

  - ESP32 GPIO 25 <- RPI_S0 (Input from RPi for channel bit 0) (INPUT_PULLUP)
  - ESP32 GPIO 26 <- RPI_S1 (Input from RPi for channel bit 1) (INPUT_PULLUP)
  - ESP32 GPIO 27 <- RPI_S2 (Input from RPi for channel bit 2) (INPUT_PULLUP)
  - ESP32 GPIO 33 <- RPI_OVERRIDE (Input from RPi to enable auto mode) (INPUT_PULLUP)

  - ESP32 USB Serial (TX0, RX0) <- PC running PySatTrack for Serial control.
*/

#include <WiFi.h>
#include <WebServer.h>

// --- Configuration ---
const char* ssid = "RF_Switch_Control";
const char* password = "password123";

// GPIO pins for switch control lines (OUTPUTS)
const int S0_PIN_OUT = 18;
const int S1_PIN_OUT = 19;
const int S2_PIN_OUT = 21;

// GPIO pins for Raspberry Pi control lines (INPUTS)
const int RPI_S0_PIN_IN = 25;
const int RPI_S1_PIN_IN = 26;
const int RPI_S2_PIN_IN = 27;
const int RPI_OVERRIDE_PIN_IN = 33;

WebServer server(80);

// --- State Variables ---
int currentChannel = 1;
enum ControlMode { MANUAL_WIFI, AUTOMATED_SERIAL, AUTOMATED_GPIO };
ControlMode currentMode = MANUAL_WIFI;

// --- Web Page HTML (Unchanged from your version) ---
const char INDEX_HTML[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
    <title>RF Switch Control</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial, sans-serif; background-color: #2c3e50; color: #ecf0f1; text-align: center; }
        h1 { color: #3498db; }
        .container { max-width: 400px; margin: 20px auto; padding: 20px; background-color: #34495e; border-radius: 8px; }
        .channel-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
        .btn { background-color: #3498db; border: none; color: white; padding: 20px; text-align: center;
               text-decoration: none; font-size: 16px; margin: 4px 2px; border-radius: 8px; cursor: pointer;
               transition: background-color 0.3s; }
        .btn:hover { background-color: #2980b9; }
        .active { background-color: #2ecc71 !important; font-weight: bold; }
        .disabled { background-color: #95a5a6; cursor: not-allowed; }
        #status { margin-top: 20px; font-size: 1.2em; color: #e67e22; }
    </style>
</head>
<body>
    <div class="container">
        <h1>ESP32 RF Switch Control</h1>
        <div class="channel-grid" id="grid">
            <button class="btn" onclick="setChannel(1)">NOAA (137 MHz)</button>
            <button class="btn" onclick="setChannel(2)">2M/ISS (145 MHz)</button>
            <button class="btn" onclick="setChannel(3)">VHF LEO (173 MHz)</button>
            <button class="btn" onclick="setChannel(4)">LoRa (433 MHz)</button>
            <button class="btn" onclick="setChannel(5)">ISM/LoRa (868 MHz)</button>
            <button class="btn" onclick="setChannel(6)">H-Line (1420 MHz)</button>
            <button class="btn" onclick="setChannel(7)">GOES (1690 MHz)</button>
            <button class="btn" onclick="setChannel(8)">Aux/Test</button>
        </div>
        <p id="status">Current Channel: 1 (Manual Mode)</p>
    </div>

    <script>
        function setChannel(channel) {
            fetch('/set?channel=' + channel)
                .then(response => response.json())
                .then(data => {
                    document.getElementById('status').innerText = data.message;
                    if(data.success) {
                        updateActiveButton(parseInt(data.channel));
                    }
                })
                .catch(error => console.error('Error:', error));
        }

        function updateActiveButton(activeChannel) {
            const buttons = document.querySelectorAll('.btn');
            buttons.forEach((btn, index) => {
                if ((index + 1) === activeChannel) {
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active');
                }
            });
        }
        
        function checkMode() {
            fetch('/status')
                .then(response => response.json())
                .then(data => {
                    const grid = document.getElementById('grid');
                    const statusText = document.getElementById('status');
                    statusText.innerText = `Current Channel: ${data.channel} (${data.mode})`;
                    updateActiveButton(data.channel);

                    if (data.mode !== 'Manual (Wi-Fi)') {
                        grid.style.pointerEvents = 'none'; // Disable buttons
                        document.querySelectorAll('.btn').forEach(b => b.classList.add('disabled'));
                    } else {
                        grid.style.pointerEvents = 'auto'; // Enable buttons
                        document.querySelectorAll('.btn').forEach(b => b.classList.remove('disabled'));
                    }
                });
        }
        
        window.onload = function() {
            checkMode();
            setInterval(checkMode, 2000);
        };
    </script>
</body>
</html>
)rawliteral";

// --- Function to set the physical switch state ---
void setSwitchChannel(int channel) {
  if (channel < 1 || channel > 8) return;
  
  int binary_code = channel - 1;

  digitalWrite(S0_PIN_OUT, (binary_code & 1));
  digitalWrite(S1_PIN_OUT, (binary_code & 2) >> 1);
  digitalWrite(S2_PIN_OUT, (binary_code & 4) >> 2);

  if (currentChannel != channel) {
    currentChannel = channel;
    String modeStr = "Unknown";
    if (currentMode == AUTOMATED_GPIO) modeStr = "GPIO";
    else if (currentMode == AUTOMATED_SERIAL) modeStr = "Serial";
    else if (currentMode == MANUAL_WIFI) modeStr = "Wi-Fi";
    
    Serial.printf("Switched to Channel: %d (Control: %s)\n", currentChannel, modeStr.c_str());
  }
}

// --- Web Server Handlers ---
void handleRoot() {
  server.send(200, "text/html", INDEX_HTML);
}

void handleStatus() {
  String modeStr = "Manual (Wi-Fi)";
  if (currentMode == AUTOMATED_GPIO) modeStr = "Automated (GPIO)";
  else if (currentMode == AUTOMATED_SERIAL) modeStr = "Automated (Serial)";
  
  String json = "{\"channel\": " + String(currentChannel) + ", \"mode\": \"" + modeStr + "\"}";
  server.send(200, "application/json", json);
}

void handleSet() {
  if (currentMode != MANUAL_WIFI) {
    server.send(403, "application/json", "{\"success\": false, \"message\": \"Control is locked by an automated source.\"}");
    return;
  }
  
  String channelStr = server.arg("channel");
  if (channelStr != "") {
    int channel = channelStr.toInt();
    if (channel >= 1 && channel <= 8) {
      setSwitchChannel(channel);
      String message = "{\"success\": true, \"channel\": " + String(currentChannel) + ", \"message\": \"Switched to Channel " + String(currentChannel) + "\"}";
      server.send(200, "application/json", message);
    } else {
      server.send(400, "text/plain", "Invalid Channel");
    }
  }
}

void handleNotFound() {
  server.send(404, "text/plain", "Not found");
}

// --- NEW: Function to handle incoming Serial commands ---
void handleSerialCommands() {
  if (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    
    if (command.startsWith("SET:")) {
      int channel = command.substring(4).toInt();
      if (channel >= 1 && channel <= 8) {
        currentMode = AUTOMATED_SERIAL; // Take control
        setSwitchChannel(channel);
        Serial.println("OK"); // Acknowledge command
      } else {
        Serial.println("ERROR: Invalid channel");
      }
    } else if (command.startsWith("ID?")) {
        Serial.println("ESP32 RF Switch v3.0");
    }
  }
}

void setup() {
  Serial.begin(115200);
  
  pinMode(S0_PIN_OUT, OUTPUT);
  pinMode(S1_PIN_OUT, OUTPUT);
  pinMode(S2_PIN_OUT, OUTPUT);

  pinMode(RPI_S0_PIN_IN, INPUT_PULLUP);
  pinMode(RPI_S1_PIN_IN, INPUT_PULLUP);
  pinMode(RPI_S2_PIN_IN, INPUT_PULLUP);
  pinMode(RPI_OVERRIDE_PIN_IN, INPUT_PULLUP);

  Serial.println("Setting default channel to 1...");
  setSwitchChannel(currentChannel);
  
  Serial.print("Starting AP ");
  Serial.println(ssid);
  WiFi.softAP(ssid, password);
  IPAddress myIP = WiFi.softAPIP();
  Serial.print("AP IP address: ");
  Serial.println(myIP);

  server.on("/", HTTP_GET, handleRoot);
  server.on("/set", HTTP_GET, handleSet);
  server.on("/status", HTTP_GET, handleStatus);
  server.onNotFound(handleNotFound);

  server.begin();
  Serial.println("HTTP server started. Listening for GPIO, Serial, and Web control.");
}

void loop() {
  // --- PRIORITY 1: Check for Raspberry Pi GPIO Override ---
  if (digitalRead(RPI_OVERRIDE_PIN_IN) == LOW) {
    if (currentMode != AUTOMATED_GPIO) {
      currentMode = AUTOMATED_GPIO;
      Serial.println("Raspberry Pi has taken control (GPIO Mode).");
    }
    int s0 = digitalRead(RPI_S0_PIN_IN);
    int s1 = digitalRead(RPI_S1_PIN_IN);
    int s2 = digitalRead(RPI_S2_PIN_IN);
    int binary_code = (s2 << 2) | (s1 << 1) | s0;
    int targetChannel = binary_code + 1;
    setSwitchChannel(targetChannel);
  } else {
    // If GPIO override is released, fall back to other modes
    if (currentMode == AUTOMATED_GPIO) {
      currentMode = MANUAL_WIFI; // Default to Wi-Fi after RPi releases control
      Serial.println("Raspberry Pi has released control. Reverting to Manual/Serial mode.");
    }
    
    // --- PRIORITY 2: Check for PC Serial Commands ---
    // Only listen to Serial if not in GPIO override mode.
    handleSerialCommands();

    // --- PRIORITY 3: Handle Wi-Fi Web Server Requests ---
    server.handleClient();
  }
  
  delay(50);
}
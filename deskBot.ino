/*****************************************************************
 * DeskBot – RoboEyes modular demo  (Touch-to-Wake WiFi edition)
 *   h = happy     n = neutral     t = tired     a = angry
 *   l = laugh     c = confused    s = look-around scan
 *   r = turn right q = turn left  m = center head
 *   Touch sensor on G26 for activation/interaction
 *****************************************************************/
#include <WiFi.h>
#include <WebServer.h>
#include <ArduinoJson.h>
#include <Adafruit_SSD1306.h>
#include <ESP32Servo.h>

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET    -1
#define SERVO_PIN     14
#define TOUCH_PIN     26

// WiFi credentials - UPDATE THESE!
const char* ssid = "RAY";
const char* password = "success@2020";

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);
WebServer server(80);

#include <FluxGarage_RoboEyes.h>
roboEyes eyes;

// Servo control
Servo headServo;
int centerPosition = 90;    // Center position (adjust as needed)
int leftPosition = 45;      // Left turn position
int rightPosition = 135;    // Right turn position
int currentPosition = 90;   // Track current position

// Touch sensor variables
bool touchState = false;
bool lastTouchState = false;
unsigned long lastTouchTime = 0;
unsigned long touchDebounce = 50;  // 50ms debounce
int touchCount = 0;

// Double tap and long press detection
unsigned long firstTapTime = 0;
unsigned long touchPressTime = 0;
unsigned long touchReleaseTime = 0;
int tapCount = 0;
bool longPressDetected = false;
bool touchPressed = false;

const unsigned long DOUBLE_TAP_WINDOW = 500;  // 500ms window for double tap
const unsigned long LONG_PRESS_DURATION = 2000;  // 2 seconds for long press
const unsigned long TAP_TIMEOUT = 800;  // Reset tap count after this time

// Sleep/Wake system
bool isAwake = false;
unsigned long lastActivityTime = 0;
unsigned long sleepTimeout = 30000;  // 30 seconds of inactivity before sleep
bool pendingWake = false;  // Flag for Python backend to know robot wants to wake

/* ───── Sleep/Wake Functions ───── */
void goToSleep() {
  if (isAwake) {
    Serial.println("😴 Robot going to sleep...");
    isAwake = false;
    
    // Turn off display
    display.clearDisplay();
    display.display();
    display.ssd1306_command(SSD1306_DISPLAYOFF);
    
    // Center head and stop servo
    centerHead();
    headServo.detach();  // Save power
    
    Serial.println("💤 Robot is sleeping. Touch to wake up.");
  }
}

void wakeUp() {
  if (!isAwake) {
    Serial.println("🌅 Robot waking up...");
    isAwake = true;
    pendingWake = true;  // Signal to Python backend
    lastActivityTime = millis();
    
    // Turn on display
    display.ssd1306_command(SSD1306_DISPLAYON);
    display.clearDisplay();
    display.display();
    
    // Re-attach servo
    headServo.attach(SERVO_PIN);
    headServo.write(centerPosition);
    delay(500);
    
    // Initialize eyes
    eyes.begin(SCREEN_WIDTH, SCREEN_HEIGHT, 100);
    eyes.setAutoblinker(ON, 3, 2);
    setEmotion(HAPPY);  // Happy to be awake
    
    // Wake up animation
    delay(1000);
    laugh();
    delay(500);
    setEmotion(DEFAULT);
    
    Serial.println("✨ Robot is awake and ready!");
  }
  lastActivityTime = millis();  // Reset activity timer
}

void checkSleepTimeout() {
  if (isAwake && (millis() - lastActivityTime > sleepTimeout)) {
    goToSleep();
  }
}

/* ───── helpers ───── */
void setEmotion(uint8_t mood) { 
  if (isAwake) {
    eyes.setMood(mood); 
    lastActivityTime = millis();
  }
}

void laugh() { 
  if (isAwake) {
    eyes.anim_laugh(); 
    lastActivityTime = millis();
  }
}

void confusedShake() { 
  if (isAwake) {
    setEmotion(DEFAULT); 
    eyes.anim_confused(); 
    lastActivityTime = millis();
  }
}

// Servo movement functions
void turnHeadLeft() {
  if (!isAwake) return;
  Serial.println("Turning head left");
  for (int pos = currentPosition; pos >= leftPosition; pos--) {
    headServo.write(pos);
    currentPosition = pos;
    delay(15);
  }
  lastActivityTime = millis();
}

void turnHeadRight() {
  if (!isAwake) return;
  Serial.println("Turning head right");
  for (int pos = currentPosition; pos <= rightPosition; pos++) {
    headServo.write(pos);
    currentPosition = pos;
    delay(15);
  }
  lastActivityTime = millis();
}

void centerHead() {
  Serial.println("Centering head");
  int target = centerPosition;
  if (currentPosition < target) {
    for (int pos = currentPosition; pos <= target; pos++) {
      headServo.write(pos);
      currentPosition = pos;
      delay(15);
    }
  } else {
    for (int pos = currentPosition; pos >= target; pos--) {
      headServo.write(pos);
      currentPosition = pos;
      delay(15);
    }
  }
  if (isAwake) lastActivityTime = millis();
}

void lookAround() {
  if (!isAwake) return;
  // Enhanced look around with head movement
  turnHeadLeft();
  eyes.setPosition(W);       delay(300);
  eyes.setPosition(DEFAULT); delay(300);
  
  centerHead();
  eyes.setPosition(DEFAULT); delay(300);
  
  turnHeadRight();
  eyes.setPosition(E);       delay(300);
  eyes.setPosition(DEFAULT); delay(300);
  
  centerHead();
  lastActivityTime = millis();
}

// Touch sensor functions
void handleDoubleTap() {
  Serial.println("👆👆 Double tap detected!");
  
  if (!isAwake) {
    Serial.println("💤 Double tap waking up robot...");
    wakeUp();
  } else {
    // If already awake, treat as interaction
    touchCount++;
    lastActivityTime = millis();
    
    // Cycle through responses
    switch (touchCount % 4) {
      case 0:
        setEmotion(HAPPY);
        laugh();
        Serial.println("Double tap response: Happy laugh");
        break;
      case 1:
        lookAround();
        Serial.println("Double tap response: Look around");
        break;
      case 2:
        setEmotion(ANGRY);
        delay(1000);
        setEmotion(DEFAULT);
        Serial.println("Double tap response: Angry");
        break;
      case 3:
        // Head shake
        turnHeadLeft();
        delay(200);
        turnHeadRight();
        delay(200);
        centerHead();
        Serial.println("Double tap response: Head shake");
        break;
    }
  }
}

void handleLongPress() {
  Serial.println("✋ Long press detected (2 seconds)!");
  
  if (isAwake) {
    Serial.println("😴 Long press putting robot to sleep...");
    goToSleep();
  } else {
    Serial.println("Robot is already sleeping");
  }
}

void updateTouchSensor() {
  bool currentTouch = digitalRead(TOUCH_PIN);
  
  // Debouncing
  if (currentTouch != lastTouchState) {
    lastTouchTime = millis();
  }
  
  if ((millis() - lastTouchTime) > touchDebounce) {
    // Detect touch press (rising edge)
    if (currentTouch == HIGH && touchState == LOW) {
      Serial.println("📟 Touch press detected");
      touchPressed = true;
      touchPressTime = millis();
      longPressDetected = false;
      
      // Handle tap counting for double tap
      unsigned long currentTime = millis();
      
      if (tapCount == 0) {
        // First tap
        firstTapTime = currentTime;
        tapCount = 1;
        Serial.println("First tap registered");
      } else if (tapCount == 1 && (currentTime - firstTapTime) < DOUBLE_TAP_WINDOW) {
        // Second tap within window - double tap!
        Serial.println("👆👆 Processing double tap...");
        tapCount = 0;  // Reset
        
        // Reset long press detection to prevent false triggers
        touchPressed = false;
        longPressDetected = true;  // Prevent long press detection
        
        handleDoubleTap();
      } else {
        // Too late for double tap, reset
        firstTapTime = currentTime;
        tapCount = 1;
        Serial.println("Tap timeout, reset to first tap");
      }
    }
    
    // Detect touch release (falling edge)
    if (currentTouch == LOW && touchState == HIGH) {
      Serial.println("📟 Touch release detected");
      unsigned long pressDuration = 0;
      
      if (touchPressed) {
        touchReleaseTime = millis();
        pressDuration = touchReleaseTime - touchPressTime;
        Serial.print("Touch duration: ");
        Serial.print(pressDuration);
        Serial.println("ms");
        
        // Check if it was a long press (only if not already detected)
        if (pressDuration >= LONG_PRESS_DURATION && !longPressDetected) {
          longPressDetected = true;
          tapCount = 0;  // Reset tap count
          handleLongPress();
        }
      }
      
      // Always reset touch state on release
      touchPressed = false;
    }
    
    // Update touch state
    touchState = currentTouch;
  }
  
  lastTouchState = currentTouch;
  
  // Reset tap count after timeout
  if (tapCount > 0 && (millis() - firstTapTime) > TAP_TIMEOUT) {
    tapCount = 0;
    Serial.println("Tap count reset due to timeout");
  }
  
  // Check for ongoing long press (only if currently pressed and not already detected)
  if (touchPressed && !longPressDetected && touchState == HIGH && (millis() - touchPressTime) >= LONG_PRESS_DURATION) {
    longPressDetected = true;
    tapCount = 0;  // Reset tap count
    Serial.println("Long press detected during hold");
    handleLongPress();
  }
}

// Execute robot command - only if awake
String executeCommand(char command) {
  if (!isAwake) {
    return "Robot is sleeping - touch to wake up";
  }
  
  lastActivityTime = millis();  // Reset sleep timer on any command
  
  switch (command) {
    case 'h': setEmotion(HAPPY);   return "Happy emotion set";
    case 'n': setEmotion(DEFAULT); return "Neutral emotion set";
    case 't': setEmotion(TIRED);   return "Tired emotion set";
    case 'a': setEmotion(ANGRY);   return "Angry emotion set";
    case 'l': setEmotion(HAPPY); laugh(); return "Laughing";
    case 'c': confusedShake();     return "Confused expression";
    case 's': lookAround();        return "Looking around";
    case 'r': turnHeadRight();     return "Head turned right";
    case 'q': turnHeadLeft();      return "Head turned left";
    case 'm': centerHead();        return "Head centered";
    case 'w': wakeUp();            return "Robot awakened";
    case 'z': goToSleep();         return "Robot going to sleep";
    default:  return "Unknown command";
  }
}

// Web server route handlers
void handleRoot() {
  String html = "<!DOCTYPE html>";
  html += "<html>";
  html += "<head>";
  html += "<title>RubuDeskBot Control</title>";
  html += "<meta name='viewport' content='width=device-width, initial-scale=1'>";
  html += "<style>";
  html += "body { font-family: Arial; text-align: center; margin: 50px; }";
  html += "button { padding: 15px 20px; margin: 10px; font-size: 16px; border: none; border-radius: 5px; cursor: pointer; }";
  html += ".emotion { background-color: #4CAF50; color: white; }";
  html += ".head { background-color: #2196F3; color: white; }";
  html += ".action { background-color: #FF9800; color: white; }";
  html += ".touch { background-color: #9C27B0; color: white; }";
  html += ".power { background-color: #E91E63; color: white; }";
  html += "h1 { color: #333; }";
  html += ".status { margin: 20px; padding: 10px; background-color: #f0f0f0; border-radius: 5px; }";
  html += ".touch-status { margin: 10px; padding: 10px; border-radius: 5px; }";
  html += ".wake-status { margin: 10px; padding: 10px; border-radius: 5px; font-weight: bold; }";
  html += ".awake { background-color: #E8F5E8; border: 2px solid #4CAF50; }";
  html += ".sleeping { background-color: #F3E5F5; border: 2px solid #9C27B0; }";
  html += ".touched { background-color: #E8F5E8; border: 2px solid #4CAF50; }";
  html += ".not-touched { background-color: #FFF3E0; border: 2px solid #FF9800; }";
  html += ".disabled { opacity: 0.5; pointer-events: none; }";
  html += "</style>";
  html += "</head>";
  html += "<body>";
  html += "<h1>🤖 RubuDeskBot Control Panel</h1>";
  html += "<div class='status'>";
  html += "<p><strong>Status:</strong> Connected to " + WiFi.localIP().toString() + "</p>";
  html += "<p><strong>Current Position:</strong> <span id='position'>Center</span></p>";
  html += "</div>";
  html += "<div id='wake-status' class='wake-status sleeping'>";
  html += "<p><strong>Robot State:</strong> <span id='wake-state'>Sleeping 😴</span></p>";
  html += "<p><em>Double-tap sensor to wake up!</em></p>";
  html += "<p><em>Hold for 2 seconds to sleep</em></p>";
  html += "</div>";
  html += "<div id='touch-status' class='touch-status not-touched'>";
  html += "<p><strong>Touch Sensor:</strong> <span id='touch-state'>Not Touched</span></p>";
  html += "<p><strong>Touch Count:</strong> <span id='touch-count'>0</span></p>";
  html += "</div>";
  html += "<div id='controls'>";
  html += "<h3>😊 Emotions</h3>";
  html += "<button class='emotion' onclick='sendCommand(\"h\")'>Happy</button>";
  html += "<button class='emotion' onclick='sendCommand(\"n\")'>Neutral</button>";
  html += "<button class='emotion' onclick='sendCommand(\"t\")'>Tired</button>";
  html += "<button class='emotion' onclick='sendCommand(\"a\")'>Angry</button>";
  html += "<h3>🎭 Actions</h3>";
  html += "<button class='action' onclick='sendCommand(\"l\")'>Laugh</button>";
  html += "<button class='action' onclick='sendCommand(\"c\")'>Confused</button>";
  html += "<button class='action' onclick='sendCommand(\"s\")'>Look Around</button>";
  html += "<h3>🔄 Head Movement</h3>";
  html += "<button class='head' onclick='sendCommand(\"q\")'>&lt; Left</button>";
  html += "<button class='head' onclick='sendCommand(\"m\")'>Center</button>";
  html += "<button class='head' onclick='sendCommand(\"r\")'>Right &gt;</button>";
  html += "<h3>⚡ Power Control</h3>";
  html += "<button class='power' onclick='sendCommand(\"w\")'>Wake Up</button>";
  html += "<button class='power' onclick='sendCommand(\"z\")'>Sleep</button>";
  html += "</div>";
  html += "<h3>🤚 Touch Test</h3>";
  html += "<button class='touch' onclick='refreshStatus()'>Refresh Status</button>";
  html += "<script>";
  html += "let isAwake = false;";
  html += "function sendCommand(cmd) {";
  html += "  fetch('/command', {";
  html += "    method: 'POST',";
  html += "    headers: {'Content-Type': 'application/json'},";
  html += "    body: JSON.stringify({command: cmd})";
  html += "  })";
  html += "  .then(response => response.json())";
  html += "  .then(data => {";
  html += "    console.log('Response:', data);";
  html += "    if (data.status === 'success') {";
  html += "      updatePosition(cmd);";
  html += "      setTimeout(refreshStatus, 500);";  // Refresh after command
  html += "    }";
  html += "  })";
  html += "  .catch(error => console.error('Error:', error));";
  html += "}";
  html += "function updatePosition(cmd) {";
  html += "  const pos = document.getElementById('position');";
  html += "  switch(cmd) {";
  html += "    case 'q': pos.textContent = 'Left'; break;";
  html += "    case 'r': pos.textContent = 'Right'; break;";
  html += "    case 'm': pos.textContent = 'Center'; break;";
  html += "  }";
  html += "}";
  html += "function refreshStatus() {";
  html += "  fetch('/status')";
  html += "  .then(response => response.json())";
  html += "  .then(data => {";
  html += "    document.getElementById('touch-state').textContent = data.touch_state ? 'Touched!' : 'Not Touched';";
  html += "    document.getElementById('touch-count').textContent = data.touch_count;";
  html += "    const touchDiv = document.getElementById('touch-status');";
  html += "    touchDiv.className = 'touch-status ' + (data.touch_state ? 'touched' : 'not-touched');";
  html += "    isAwake = data.is_awake;";
  html += "    const wakeDiv = document.getElementById('wake-status');";
  html += "    const wakeState = document.getElementById('wake-state');";
  html += "    const controls = document.getElementById('controls');";
  html += "    if (isAwake) {";
  html += "      wakeDiv.className = 'wake-status awake';";
  html += "      wakeState.textContent = 'Awake & Active ✨';";
  html += "      controls.classList.remove('disabled');";
  html += "    } else {";
  html += "      wakeDiv.className = 'wake-status sleeping';";
  html += "      wakeState.textContent = 'Sleeping 😴';";
  html += "      controls.classList.add('disabled');";
  html += "    }";
  html += "  })";
  html += "  .catch(error => console.error('Error:', error));";
  html += "}";
  html += "setInterval(refreshStatus, 1000);";  // Auto-refresh every second
  html += "refreshStatus();";  // Initial load
  html += "</script>";
  html += "</body>";
  html += "</html>";
  
  server.send(200, "text/html", html);
}

void handleCommand() {
  if (server.method() != HTTP_POST) {
    server.send(405, "application/json", "{\"error\":\"Method not allowed\"}");
    return;
  }

  String body = server.arg("plain");
  StaticJsonDocument<200> doc;
  DeserializationError error = deserializeJson(doc, body);

  if (error) {
    server.send(400, "application/json", "{\"error\":\"Invalid JSON\"}");
    return;
  }

  if (!doc.containsKey("command")) {
    server.send(400, "application/json", "{\"error\":\"Missing command field\"}");
    return;
  }

  String commandStr = doc["command"];
  if (commandStr.length() != 1) {
    server.send(400, "application/json", "{\"error\":\"Command must be single character\"}");
    return;
  }

  char command = commandStr.charAt(0);
  String result = executeCommand(command);
  
  StaticJsonDocument<200> response;
  response["status"] = "success";
  response["command"] = commandStr;
  response["message"] = result;
  response["timestamp"] = millis();

  String responseStr;
  serializeJson(response, responseStr);
  
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.sendHeader("Access-Control-Allow-Methods", "POST, GET, OPTIONS");
  server.sendHeader("Access-Control-Allow-Headers", "Content-Type");
  server.send(200, "application/json", responseStr);

  Serial.println("Command executed: " + commandStr + " -> " + result);
}

void handleStatus() {
  StaticJsonDocument<400> status;
  status["device"] = "RubuDeskBot";
  status["version"] = "2.0.0-touch-wake";
  status["uptime"] = millis();
  status["wifi_ssid"] = WiFi.SSID();
  status["ip_address"] = WiFi.localIP().toString();
  status["rssi"] = WiFi.RSSI();
  status["head_position"] = currentPosition;
  status["touch_state"] = touchState;
  status["touch_count"] = touchCount;
  status["available_commands"] = "h,n,t,a,l,c,s,r,q,m,w,z";
  status["is_awake"] = isAwake;
  status["last_activity"] = lastActivityTime;
  status["pending_wake"] = pendingWake;

  String responseStr;
  serializeJson(status, responseStr);
  
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.send(200, "application/json", responseStr);
}

void handleWake() {
  // Endpoint for Python backend to check for wake events
  StaticJsonDocument<200> response;
  response["wake_requested"] = pendingWake;
  response["is_awake"] = isAwake;
  response["timestamp"] = millis();
  
  if (pendingWake) {
    pendingWake = false;  // Clear the flag after Python reads it
  }
  
  String responseStr;
  serializeJson(response, responseStr);
  
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.send(200, "application/json", responseStr);
}

void handleOptions() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.sendHeader("Access-Control-Allow-Methods", "POST, GET, OPTIONS");
  server.sendHeader("Access-Control-Allow-Headers", "Content-Type");
  server.send(200);
}

void setup() {
  Serial.begin(9600);
  Serial.println("🤖 RubuDeskBot Touch-to-Wake Edition Starting...");

  // Initialize display (but keep it off initially)
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println(F("SSD1306 init failed")); 
    while (true);
  }
  
  // Start with display off (sleep mode)
  display.clearDisplay();
  display.display();
  display.ssd1306_command(SSD1306_DISPLAYOFF);

  // Initialize servo (but don't attach yet to save power)
  currentPosition = centerPosition;

  // Initialize touch sensor
  pinMode(TOUCH_PIN, INPUT);  // TTP223 outputs HIGH when touched
  lastTouchState = digitalRead(TOUCH_PIN);
  Serial.println("Touch sensor initialized on pin " + String(TOUCH_PIN));

  // Connect to WiFi
  Serial.print("Connecting to WiFi");
  WiFi.begin(ssid, password);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(1000);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println();
    Serial.println("✅ WiFi Connected!");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
    Serial.print("Access control panel: http://");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println();
    Serial.println("❌ WiFi Connection Failed!");
    Serial.println("Please check your credentials and try again.");
    return;
  }

  // Setup web server routes
  server.on("/", HTTP_GET, handleRoot);
  server.on("/command", HTTP_POST, handleCommand);
  server.on("/command", HTTP_OPTIONS, handleOptions);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/status", HTTP_OPTIONS, handleOptions);
  server.on("/wake", HTTP_GET, handleWake);  // New endpoint for Python backend
  server.on("/wake", HTTP_OPTIONS, handleOptions);

  // Start server
  server.begin();
  Serial.println("🌐 Web server started!");
  Serial.println("Available endpoints:");
  Serial.println("  GET  /        - Control panel");
  Serial.println("  POST /command - Send robot commands");
  Serial.println("  GET  /status  - Device status");
  Serial.println("  GET  /wake    - Wake event polling");
  Serial.println("💤 Robot starting in SLEEP mode");
  Serial.println("🤚 Touch sensor to wake up on GPIO " + String(TOUCH_PIN));
}

void loop() {
  server.handleClient();  // handle web requests
  updateTouchSensor();    // update touch sensor state
  checkSleepTimeout();    // check and manage sleep timeout
  
  // Only update eyes if awake
  if (isAwake) {
    eyes.update();        // keep animations flowing
  }
  
  // Handle WiFi reconnection
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi disconnected, attempting reconnection...");
    WiFi.reconnect();
    delay(5000);
  }
}

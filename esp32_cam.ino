/*
  ESP32-CAM -> FastAPI /recognize (multipart/form-data)
  - Click "Capture & Send" to take a photo and POST it to the server
  - Replace SERVER_HOST with your PC's LAN IP (NOT 127.0.0.1)
*/

#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>

// ---------- Wi-Fi ----------
const char* WIFI_SSID = "RAY";
const char* WIFI_PASS = "success@2020";

// ---------- Your FastAPI server ----------
const char* SERVER_HOST = "192.168.29.42";   // <-- CHANGE THIS (PC LAN IP)
const uint16_t SERVER_PORT = 8000;
const char* SERVER_PATH = "/recognize";

// ---------- Camera pins: AI-Thinker ----------
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

#define FLASH_LED_GPIO     4   // white LED on the board

WebServer server(80);

// ---------- HTML ----------
const char INDEX_HTML[] PROGMEM = R"HTML(
<!doctype html><html><head><meta name=viewport content="width=device-width,initial-scale=1">
<title>ESP32-CAM → /recognize</title>
<style>body{font-family:system-ui;margin:16px}pre{white-space:pre-wrap;background:#111;color:#0f0;padding:12px;border-radius:8px}</style>
</head><body>
<h2>ESP32-CAM → FastAPI /recognize</h2>
<button onclick="send()">Capture & Send</button>
<p id=stat>Idle</p>
<pre id=out></pre>
<script>
async function send(){
  document.getElementById('stat').textContent='Capturing…';
  let r = await fetch('/capture', {method:'POST'});
  document.getElementById('stat').textContent = r.ok ? 'OK' : ('HTTP '+r.status);
  document.getElementById('out').textContent = await r.text();
}
</script>
</body></html>
)HTML";

// ---------- Helpers ----------
bool postMultipartJpeg(const uint8_t* data, size_t len, String& bodyOut, int& codeOut) {
  WiFiClient client;
  if (!client.connect(SERVER_HOST, SERVER_PORT)) {
    Serial.println("connect() failed");
    return false;
  }

  String boundary = "----ESP32CamBoundary";
  String head =
      "--" + boundary + "\r\n"
      "Content-Disposition: form-data; name=\"image\"; filename=\"esp32.jpg\"\r\n"
      "Content-Type: image/jpeg\r\n\r\n";
  String tail = "\r\n--" + boundary + "--\r\n";

  size_t contentLen = head.length() + len + tail.length();

  // Request line + headers
  client.printf("POST %s HTTP/1.1\r\n", SERVER_PATH);
  client.printf("Host: %s:%u\r\n", SERVER_HOST, SERVER_PORT);
  client.printf("Content-Type: multipart/form-data; boundary=%s\r\n", boundary.c_str());
  client.printf("Content-Length: %u\r\n", (unsigned)contentLen);
  client.print("Connection: close\r\n\r\n");

  // Body
  client.print(head);
  size_t sent = 0;
  while (sent < len) {                   // write in chunks (safer for big frames)
    size_t chunk = min((size_t)2048, len - sent);
    client.write(data + sent, chunk);
    sent += chunk;
  }
  client.print(tail);

  // Read response
  uint32_t t0 = millis();
  while (!client.available() && millis() - t0 < 8000) delay(10);
  if (!client.available()) { Serial.println("No response"); return false; }

  // Parse status line
  String status = client.readStringUntil('\n'); // e.g. HTTP/1.1 200 OK
  status.trim();
  Serial.println(status);
  int httpCode = 0;
  int sp1 = status.indexOf(' ');
  if (sp1 > 0) httpCode = status.substring(sp1 + 1).toInt();
  codeOut = httpCode;

  // Skip headers
  while (client.connected()) {
    String line = client.readStringUntil('\n');
    if (line == "\r") break;
  }

  // Body
  bodyOut = client.readString();
  client.stop();
  return true;
}

void startCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;   config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;   config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;   config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;   config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM; config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM; config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  if(psramFound()){
    config.frame_size = FRAMESIZE_VGA;    // 640x480
    config.jpeg_quality = 12;             // 10–15 is fine
    config.fb_count = 2;
  } else {
    config.frame_size = FRAMESIZE_QVGA;   // 320x240
    config.jpeg_quality = 15;
    config.fb_count = 1;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", err);
    while(true) delay(1000);
  }
}

// ---------- HTTP handlers ----------
void handle_root() { server.send_P(200, "text/html", INDEX_HTML); }

void handle_capture_post() {
  // flash
  pinMode(FLASH_LED_GPIO, OUTPUT);
  digitalWrite(FLASH_LED_GPIO, HIGH);
  delay(120);

  camera_fb_t *fb = esp_camera_fb_get();
  digitalWrite(FLASH_LED_GPIO, LOW);

  if (!fb || fb->format != PIXFORMAT_JPEG) {
    if (fb) esp_camera_fb_return(fb);
    server.send(503, "text/plain", "Capture failed");
    return;
  }

  String respBody; int httpCode = -1;
  bool ok = postMultipartJpeg(fb->buf, fb->len, respBody, httpCode);
  esp_camera_fb_return(fb);

  if (!ok) {
    server.send(502, "text/plain", "POST failed (no response)");
    return;
  }
  // Echo the server's JSON back to the browser
  const char* mime = (respBody.length() && respBody[0] == '{') ? "application/json" : "text/plain";
  server.send(httpCode == 0 ? 500 : httpCode, mime, respBody);
}

void setup() {
  pinMode(FLASH_LED_GPIO, OUTPUT);
  digitalWrite(FLASH_LED_GPIO, LOW);

  Serial.begin(115200);
  Serial.setDebugOutput(true);
  delay(500);

  startCamera();

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.printf("Connecting to %s", WIFI_SSID);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 15000) {
    delay(300); Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\nWi-Fi connected: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\nSTA failed -> starting AP");
    WiFi.mode(WIFI_AP);
    WiFi.softAP("ESP32-CAM-TEST", "12345678");
    Serial.printf("AP IP: %s\n", WiFi.softAPIP().toString().c_str());
  }

  server.on("/", HTTP_GET, handle_root);
  server.on("/capture", HTTP_POST, handle_capture_post);  // POST from page button
  server.begin();
  Serial.println("HTTP server started. Open / in your browser.");
}

void loop() { server.handleClient(); }

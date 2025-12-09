# RubuDeskBot 🤖

A cute AI-powered desk robot with voice interaction, facial expressions, and head movement capabilities - now with **wireless WiFi communication**!

## Project Overview

RubuDeskBot (RUBY) is an interactive desk companion created by Saswat Ray. The robot combines:
- **AI Voice Interaction**: Real-time conversation using OpenAI's GPT-4 Realtime API
- **Facial Expressions**: Animated eyes with various emotions (happy, sad, angry, confused, etc.)
- **Head Movement**: Servo-controlled head turning for more expressive interactions
- **Wireless Control**: WiFi-based web server for reliable network communication
- **Web Interface**: Built-in control panel accessible from any browser
- **Personality**: Cute, funny responses with physical gestures

## Hardware Components

### ESP32 Setup
- **Microcontroller**: ESP32 development board with WiFi
- **Display**: SSD1306 OLED (128x64) connected via I2C
- **Servo**: Connected to GPIO 14 for head movement
- **Libraries Required**:
  - `WiFi.h`
  - `WebServer.h`
  - `ArduinoJson.h`
  - `Adafruit_SSD1306.h`
  - `FluxGarage_RoboEyes.h` 
  - `Servo.h`

### Connections
```
ESP32 Pin  →  Component
GPIO 14    →  Servo Signal Wire
SDA        →  OLED SDA
SCL        →  OLED SCL
3.3V       →  OLED VCC
GND        →  OLED GND, Servo GND
5V         →  Servo VCC
```

## Software Architecture

```
┌─────────────────┐    WiFi/HTTP   ┌─────────────────┐
│   main.py       │ ─────────────→ │   deskBot.ino   │
│   (AI Agent)    │   REST API     │   (ESP32)       │
│                 │                │                 │
│ - Voice Input   │                │ - Web Server    │
│ - AI Processing │                │ - Eye Animations│  
│ - HTTP Requests │                │ - Head Movement │
│ - Auto Discovery│                │ - WiFi Control  │
└─────────────────┘                └─────────────────┘
```

## Installation & Setup

### 1. Python Environment
```bash
# Install dependencies
pip install -r requirements.txt
```

### 2. Telegram Bot Setup (for Face Recognition Notifications)
1. **Create a Telegram Bot**:
   - Message @BotFather on Telegram
   - Send `/newbot` and follow instructions
   - Save the bot token you receive

2. **Get Your Chat ID**:
   - Start a conversation with your new bot
   - Send any message to the bot
   - Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   - Find your chat ID in the response

3. **Set Environment Variables**:
   ```bash
   # Windows
   set TELEGRAM_BOT_TOKEN=your_bot_token_here
   set TELEGRAM_CHAT_ID=your_chat_id_here
   
   # Linux/Mac
   export TELEGRAM_BOT_TOKEN=your_bot_token_here
   export TELEGRAM_CHAT_ID=your_chat_id_here
   ```

   Or create a `.env` file in the project root:
   ```
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   TELEGRAM_CHAT_ID=your_chat_id_here
   ```

### 3. Arduino Setup
1. Install Arduino IDE with ESP32 board support
2. Install required libraries:
   - Adafruit SSD1306
   - FluxGarage RoboEyes
   - ArduinoJson
3. **Configure WiFi**: Edit `deskBot.ino` and update WiFi credentials:
   ```cpp
   const char* ssid = "YOUR_WIFI_SSID";
   const char* password = "YOUR_WIFI_PASSWORD";
   ```
4. Upload `deskBot.ino` to your ESP32

### 4. Network Configuration
1. Ensure your computer and ESP32 are on the same WiFi network
2. After uploading, check Arduino Serial Monitor for IP address
3. The robot will show a happy face when WiFi connects successfully
4. Note the IP address displayed in Serial Monitor

## Usage

### Starting the System

#### Main AI Assistant
```bash
python main.py
```

The system will:
1. Auto-scan network for RubuDeskBot
2. Connect to robot via WiFi
3. Display robot status and IP address
4. Start voice recording and AI interaction

#### Face Recognition Server (Optional)
```bash
uvicorn new_server:app --host 0.0.0.0 --port 8000
```

The face recognition server will:
1. Start FastAPI server on port 8000
2. Provide `/recognize` endpoint for face detection
3. Send Telegram notifications when known faces are detected
4. Return JSON with recognized faces and similarity scores

**Usage**: POST an image to `http://localhost:8000/recognize`

### Voice Commands
Simply speak to RUBY! The AI will:
- Respond with cute, short answers
- Use appropriate facial expressions
- Move head for emphasis
- Call tools to control physical gestures wirelessly

### Web Control Panel
Access the robot's built-in web interface:
1. Open browser and go to robot's IP address (e.g., `http://192.168.1.100`)
2. Use the interactive control panel to test all features
3. Real-time control of emotions and head movement

### Manual HTTP Commands
Send direct commands via HTTP POST:
```bash
curl -X POST http://ROBOT_IP/command \
  -H "Content-Type: application/json" \
  -d '{"command": "h"}'
```

## Available Robot Functions

The AI agent can call these tools during conversation:

### Emotions
- `set_robot_emotion_happy()` - Happy expression 😊
- `set_robot_emotion_neutral()` - Neutral expression 😐
- `set_robot_emotion_tired()` - Tired expression 😴
- `set_robot_emotion_angry()` - Angry expression 😠
- `make_robot_laugh()` - Animated laugh 😄
- `make_robot_confused()` - Confused expression 🤔

### Head Movement  
- `turn_robot_head_right()` - Turn head right ➡️
- `turn_robot_head_left()` - Turn head left ⬅️
- `center_robot_head()` - Center head position ⬆️
- `robot_look_around()` - Scan around with eyes and head 👀

### Status & Info
- `get_robot_info()` - Get current robot status, uptime, and connection info

## API Endpoints

The robot provides these HTTP endpoints:

### GET /
Web-based control panel interface

### POST /command
Send robot commands
```json
{
  "command": "h"
}
```

### GET /status
Get robot status information
```json
{
  "device": "RubuDeskBot",
  "version": "1.0.0-wifi",
  "uptime": 45000,
  "wifi_ssid": "MyNetwork",
  "ip_address": "192.168.1.100",
  "rssi": -45,
  "head_position": 90,
  "available_commands": "h,n,t,a,l,c,s,r,q,m"
}
```

## Troubleshooting

### Common Issues

**Robot Not Found on Network**
- Check WiFi credentials in ESP32 code
- Ensure computer and ESP32 on same network
- Check Serial Monitor for connection status
- Look for robot IP address in Serial Monitor
- Try manual IP in browser: `http://192.168.1.100`

**WiFi Connection Failed**
- Verify WiFi SSID and password in code
- Check WiFi signal strength near ESP32
- Robot shows angry face if WiFi fails
- Restart ESP32 and check Serial Monitor

**HTTP Connection Timeout**
- Robot may be busy with previous command
- Check network connectivity
- Verify robot IP address hasn't changed
- Try pinging robot IP: `ping 192.168.1.100`

**Robot Not Responding to AI**
- Check robot shows happy face on startup (WiFi connected)
- Verify AI can reach `/status` endpoint
- Check OpenAI API key validity
- Test manual web control panel first

**Audio Issues**
- Check microphone permissions
- Verify sound device settings
- Ensure 24kHz sample rate support

### Debug Steps
1. **Check ESP32 Serial Monitor** for WiFi connection status
2. **Test Web Interface** by browsing to robot IP
3. **Verify Network** with ping and status endpoint
4. **Check Python Output** for connection messages

### Network Discovery
The system tries multiple discovery methods:
1. Common IP addresses (192.168.1.100-102, etc.)
2. Network scanning for devices on port 80
3. Device identification via `/status` endpoint

## Configuration

### WiFi Settings (ESP32)
```cpp
const char* ssid = "YOUR_WIFI_SSID";        // Your WiFi network name
const char* password = "YOUR_WIFI_PASSWORD"; // Your WiFi password
```

### Network Settings (Python)
The system automatically discovers robots, but you can modify discovery in `main.py`:
```python
manual_ips = [
    "192.168.1.100", "192.168.1.101",  # Add your robot's likely IPs
    "192.168.0.100", "192.168.0.101"
]
```

## Contributing

This is a personal project by Saswat Ray. Feel free to fork and create your own version!

## License

Open source - use and modify as needed for your own robot projects! 🚀

---

## Changelog from Serial Version

- ✅ **Wireless Communication**: Replaced USB serial with WiFi HTTP
- ✅ **Web Control Panel**: Built-in browser interface
- ✅ **Auto Discovery**: Automatic robot finding on network
- ✅ **REST API**: Standard HTTP endpoints for robot control
- ✅ **Network Resilience**: Better error handling for wireless
- ✅ **Remote Access**: Control from any device on network 
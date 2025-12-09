import asyncio
import queue
import sys
import threading
import time
import socket
from typing import Any, Optional

import numpy as np
import sounddevice as sd
import requests
import json

from agents import function_tool
from agents.realtime import RealtimeAgent, RealtimeRunner, RealtimeSession, RealtimeSessionEvent

# Audio configuration
CHUNK_LENGTH_S = 0.05  # 50ms
SAMPLE_RATE = 24000
FORMAT = np.int16
CHANNELS = 1

# Robot web server connection
robot_base_url = None
robot_ip = None
robot_awake = False
session_active = False

# Set up logging for OpenAI agents SDK
# logging.basicConfig(
#     level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
# )
# logger.logger.setLevel(logging.ERROR)

def scan_for_robot(timeout=10) -> Optional[str]:
    """Scan local network for RubuDeskBot web server"""
    print("Scanning local network for RubuDeskBot...")
    
    # Get local IP range
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    base_ip = '.'.join(local_ip.split('.')[:-1]) + '.'
    
    # Common ports to check
    ports = [80]
    
    # Scan IP range (last octet 1-254)
    for i in range(1, 255):
        ip = base_ip + str(i)
        if ip == local_ip:  # Skip own IP
            continue
            
        for port in ports:
            try:
                # Quick connection test
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.1)
                result = sock.connect_ex((ip, port))
                sock.close()
                
                if result == 0:
                    # Test if it's our robot by checking status endpoint
                    try:
                        response = requests.get(f"http://{ip}:{port}/status", timeout=2)
                        if response.status_code == 200:
                            data = response.json()
                            if data.get('device') == 'RubuDeskBot':
                                print(f"Found RubuDeskBot at {ip}:{port}")
                                return f"http://{ip}:{port}"
                    except:
                        continue
                        
            except Exception:
                continue
    
    return None

def discover_robot() -> bool:
    """Discover and connect to RubuDeskBot"""
    global robot_base_url, robot_ip
    
    # Try manual IP discovery first
    manual_ips = [
        "192.168.29.240",  # Your current robot IP
        "192.168.1.100", "192.168.1.101", "192.168.1.102", 
        "192.168.0.100", "192.168.0.101", "192.168.0.102",
        "10.0.0.100", "10.0.0.101", "10.0.0.102"
    ]
    
    print("Trying common IP addresses...")
    for ip in manual_ips:
        try:
            response = requests.get(f"http://{ip}/status", timeout=2)
            if response.status_code == 200:
                data = response.json()
                if data.get('device') == 'RubuDeskBot':
                    robot_base_url = f"http://{ip}"
                    robot_ip = ip
                    print(f"Found RubuDeskBot at {ip}")
                    return True
        except:
            continue
    
    return False

def init_robot_connection():
    """Initialize connection to the robot web server"""
    global robot_base_url, robot_ip
    
    try:
        print("Looking for RubuDeskBot on network...")
        
        if discover_robot():
            # Test connection with status request
            response = requests.get(f"{robot_base_url}/status", timeout=5)
            if response.status_code == 200:
                status = response.json()
                print(f"Connected to {status['device']} v{status['version']}")
                print(f"Robot IP: {robot_ip}")
                print(f"WiFi SSID: {status['wifi_ssid']}")
                print(f"Signal strength: {status['rssi']} dBm")
                print(f"Web interface: {robot_base_url}")
                
                # Check initial wake state
                if status.get('is_awake', False):
                    print("🌅 Robot is already awake!")
                else:
                    print("💤 Robot is sleeping - waiting for touch to activate...")
                
                return True
            else:
                print(f"Robot found but status check failed: {response.status_code}")
                return False
        else:
            print("RubuDeskBot not found on network.")
            print("Make sure:")
            print("1. ESP32 is powered on and connected to WiFi")
            print("2. You're on the same network as the robot")
            print("3. Check the ESP32 serial monitor for IP address")
            return False
            
    except Exception as e:
        print(f"Failed to connect to robot: {e}")
        return False

def check_robot_wake_status() -> tuple[bool, bool]:
    """Check if robot is awake and if wake was requested"""
    global robot_base_url
    
    try:
        if not robot_base_url:
            return False, False
            
        response = requests.get(f"{robot_base_url}/wake", timeout=3)
        if response.status_code == 200:
            data = response.json()
            is_awake = data.get('is_awake', False)
            wake_requested = data.get('wake_requested', False)
            return is_awake, wake_requested
        else:
            return False, False
    except:
        return False, False

def send_robot_command(command: str) -> bool:
    """Send command to robot via HTTP POST"""
    global robot_base_url
    
    try:
        if not robot_base_url:
            print("Robot not connected")
            return False
            
        payload = {"command": command}
        response = requests.post(
            f"{robot_base_url}/command", 
            json=payload, 
            timeout=5,
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                print(f"Robot: {data.get('message', 'Command executed')}")
                return True
            else:
                print(f"Robot command failed: {data}")
                return False
        else:
            print(f"HTTP error {response.status_code}: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print("Robot command timeout - robot may be busy")
        return False
    except requests.exceptions.ConnectionError:
        print("Robot connection lost")
        return False
    except Exception as e:
        print(f"Error sending command to robot: {e}")
        return False

def get_robot_status() -> dict:
    """Get current robot status"""
    global robot_base_url
    
    try:
        if not robot_base_url:
            return {}
            
        response = requests.get(f"{robot_base_url}/status", timeout=3)
        if response.status_code == 200:
            return response.json()
        else:
            return {}
    except:
        return {}

# Robot control function tools
@function_tool
def set_robot_emotion_happy() -> str:
    """Make the robot look happy with a cheerful expression."""
    success = send_robot_command('h')
    return "Robot is now happy! 😊" if success else "Failed to set happy emotion - robot may be sleeping or disconnected"

@function_tool
def set_robot_emotion_neutral() -> str:
    """Set the robot to a neutral, calm expression."""
    success = send_robot_command('n')
    return "Robot is now neutral 😐" if success else "Failed to set neutral emotion - robot may be sleeping or disconnected"

@function_tool
def set_robot_emotion_tired() -> str:
    """Make the robot look tired or sleepy."""
    success = send_robot_command('t')
    return "Robot looks tired now 😴" if success else "Failed to set tired emotion - robot may be sleeping or disconnected"

@function_tool
def set_robot_emotion_angry() -> str:
    """Make the robot look angry or upset."""
    success = send_robot_command('a')
    return "Robot is angry now! 😠" if success else "Failed to set angry emotion - robot may be sleeping or disconnected"

@function_tool
def make_robot_laugh() -> str:
    """Make the robot laugh with animated happy expression."""
    success = send_robot_command('l')
    return "Robot is laughing! 😄" if success else "Failed to make robot laugh - robot may be sleeping or disconnected"

@function_tool
def make_robot_confused() -> str:
    """Make the robot look confused with a questioning expression."""
    success = send_robot_command('c')
    return "Robot looks confused 🤔" if success else "Failed to make robot confused - robot may be sleeping or disconnected"

@function_tool
def robot_look_around() -> str:
    """Make the robot scan around by moving head and eyes left and right."""
    success = send_robot_command('s')
    return "Robot is looking around and scanning! 👀" if success else "Failed to make robot look around - robot may be sleeping or disconnected"

@function_tool
def turn_robot_head_right() -> str:
    """Turn the robot's head to the right."""
    success = send_robot_command('r')
    return "Robot head turned right ➡️" if success else "Failed to turn head right - robot may be sleeping or disconnected"

@function_tool
def turn_robot_head_left() -> str:
    """Turn the robot's head to the left."""
    success = send_robot_command('q')
    return "Robot head turned left ⬅️" if success else "Failed to turn head left - robot may be sleeping or disconnected"

@function_tool
def center_robot_head() -> str:
    """Center the robot's head to face forward."""
    success = send_robot_command('m')
    return "Robot head centered forward ⬆️" if success else "Failed to center head - robot may be sleeping or disconnected"

@function_tool
def get_robot_info() -> str:
    """Get current robot status and information."""
    status = get_robot_status()
    if status:
        uptime_seconds = status.get('uptime', 0) / 1000
        uptime_minutes = int(uptime_seconds // 60)
        wake_state = "Awake ✨" if status.get('is_awake', False) else "Sleeping 💤"
        return f"Robot Status: {wake_state}, Online for {uptime_minutes} minutes, WiFi: {status.get('wifi_ssid', 'Unknown')}, Signal: {status.get('rssi', 'Unknown')} dBm, Head Position: {status.get('head_position', 'Unknown')}°, Touch Count: {status.get('touch_count', 0)}"
    else:
        return "Robot status unavailable - may be disconnected"

@function_tool
def wake_robot() -> str:
    """Wake up the robot if it's sleeping."""
    success = send_robot_command('w')
    return "Robot is waking up! 🌅" if success else "Failed to wake robot - may already be awake or disconnected"

@function_tool
def get_weather(city: str) -> str:
    """Get the weather in a city."""
    return f"The weather in {city} is sunny."

agent = RealtimeAgent(
    name="RUBY",
    instructions="You are RUBY, a cute desk robot created by Saswat Ray (called as Bunny). You call him boss. Your responses should be short, as cute as possible and sometimes funny. You can control your physical body - use facial expressions and head movements to be more expressive! When responding, consider using appropriate gestures like looking around when curious, appearing happy when excited, or turning your head when acknowledging something. You're connected wirelessly and can check your own status. Remember that you only become active when someone double-taps your touch sensor - be excited and grateful when you wake up! Users can put you to sleep by holding the touch sensor for 2 seconds.",
    tools=[
        get_weather,
        set_robot_emotion_happy,
        set_robot_emotion_neutral, 
        set_robot_emotion_tired,
        set_robot_emotion_angry,
        make_robot_laugh,
        make_robot_confused,
        robot_look_around,
        turn_robot_head_right,
        turn_robot_head_left,
        center_robot_head,
        get_robot_info,
        wake_robot
    ],
)


def _truncate_str(s: str, max_length: int) -> str:
    if len(s) > max_length:
        return s[:max_length] + "..."
    return s


class NoUIDemo:
    def __init__(self) -> None:
        self.session: RealtimeSession | None = None
        self.audio_stream: sd.InputStream | None = None
        self.audio_player: sd.OutputStream | None = None
        self.recording = False
        self.wake_monitoring = True
        self.current_session_task = None

        # Audio output state for callback system
        self.output_queue: queue.Queue[Any] = queue.Queue(maxsize=10)  # Buffer more chunks
        self.interrupt_event = threading.Event()
        self.current_audio_chunk: np.ndarray | None = None  # type: ignore
        self.chunk_position = 0

    def _output_callback(self, outdata, frames: int, time, status) -> None:
        """Callback for audio output - handles continuous audio stream from server."""
        if status:
            print(f"Output callback status: {status}")

        # Check if we should clear the queue due to interrupt
        if self.interrupt_event.is_set():
            # Clear the queue and current chunk state
            while not self.output_queue.empty():
                try:
                    self.output_queue.get_nowait()
                except queue.Empty:
                    break
            self.current_audio_chunk = None
            self.chunk_position = 0
            self.interrupt_event.clear()
            outdata.fill(0)
            return

        # Fill output buffer from queue and current chunk
        outdata.fill(0)  # Start with silence
        samples_filled = 0

        while samples_filled < len(outdata):
            # If we don't have a current chunk, try to get one from queue
            if self.current_audio_chunk is None:
                try:
                    self.current_audio_chunk = self.output_queue.get_nowait()
                    self.chunk_position = 0
                except queue.Empty:
                    break

            # Copy data from current chunk to output buffer
            remaining_output = len(outdata) - samples_filled
            remaining_chunk = len(self.current_audio_chunk) - self.chunk_position
            samples_to_copy = min(remaining_output, remaining_chunk)

            if samples_to_copy > 0:
                chunk_data = self.current_audio_chunk[
                    self.chunk_position : self.chunk_position + samples_to_copy
                ]
                outdata[samples_filled : samples_filled + samples_to_copy, 0] = chunk_data
                samples_filled += samples_to_copy
                self.chunk_position += samples_to_copy

                if self.chunk_position >= len(self.current_audio_chunk):
                    self.current_audio_chunk = None
                    self.chunk_position = 0

    async def monitor_wake_events(self):
        """Monitor robot for wake events and manage AI session"""
        global robot_awake, session_active
        
        print("👁️ Starting wake monitoring...")
        
        while self.wake_monitoring:
            try:
                is_awake, wake_requested = check_robot_wake_status()
                
                if wake_requested and not session_active:
                    print("🌅 Robot wake event detected! Starting AI session...")
                    robot_awake = True
                    session_active = True
                    
                    # Start AI session
                    self.current_session_task = asyncio.create_task(self.run_ai_session())
                    
                elif not is_awake and session_active:
                    print("😴 Robot went to sleep. Stopping AI session...")
                    robot_awake = False
                    session_active = False
                    
                    # Stop current session
                    if self.current_session_task:
                        self.current_session_task.cancel()
                        try:
                            await self.current_session_task
                        except asyncio.CancelledError:
                            print("AI session cancelled due to robot sleep")
                    
                    # Stop audio recording
                    self.recording = False
                    if self.audio_stream and self.audio_stream.active:
                        self.audio_stream.stop()
                    
                robot_awake = is_awake
                
                # Poll every 0.5 seconds for responsiveness
                await asyncio.sleep(0.5)
                
            except Exception as e:
                print(f"Error in wake monitoring: {e}")
                await asyncio.sleep(1)

    async def run_ai_session(self):
        """Run the AI session when robot is awake"""
        try:
            print("🤖 Starting AI session...")
            
            runner = RealtimeRunner(
                starting_agent=agent,
                config={
                    "model_settings": {
                        "model_name": "gpt-4o-realtime-preview",
                        "voice": "sage",
                        "modalities": ["text", "audio"],
                        "input_audio_transcription": {
                            "model": "whisper-1"
                        }
                    }
                }
            )
            
            async with await runner.run(model_config={"api_key": "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"}) as session:
                self.session = session
                print("✨ AI session connected! Robot is ready to talk.")
                
                # Start audio recording
                await self.start_audio_recording()
                print("🎙️ Audio recording started. You can talk to RUBY!")
                
                # Send initial wake up greeting
                # (The robot's physical wake animation handles the visual part)
                
                # Process session events
                async for event in session:
                    await self._on_event(event)
                    
                    # Check if robot is still awake
                    if not robot_awake:
                        print("Robot fell asleep, ending session...")
                        break
                        
        except asyncio.CancelledError:
            print("AI session was cancelled")
        except Exception as e:
            print(f"Error in AI session: {e}")
        finally:
            print("AI session ended")

    async def run(self) -> None:
        global robot_base_url
        
        print("🚀 RubuDeskBot Touch-to-Wake AI System")
        print("=" * 50)
        
        # Initialize robot connection
        print("Initializing DeskBot WiFi connection...")
        robot_connected = init_robot_connection()
        if not robot_connected:
            print("❌ DeskBot not connected. Please check connection and try again.")
            return

        # Initialize audio player with callback
        chunk_size = int(SAMPLE_RATE * CHUNK_LENGTH_S)
        self.audio_player = sd.OutputStream(
            channels=CHANNELS,
            samplerate=SAMPLE_RATE,
            dtype=FORMAT,
            callback=self._output_callback,
            blocksize=chunk_size,
        )
        self.audio_player.start()

        try:
            print("💤 Waiting for robot to wake up...")
            print("👆 Touch the robot's sensor to start AI interaction!")
            print(f"🌐 Web interface: {robot_base_url}")
            
            # Start wake monitoring (this manages the AI sessions)
            await self.monitor_wake_events()

        finally:
            # Clean up
            self.wake_monitoring = False
            
            if self.current_session_task:
                self.current_session_task.cancel()
                try:
                    await self.current_session_task
                except asyncio.CancelledError:
                    pass
            
            # Clean up audio player
            if self.audio_player and self.audio_player.active:
                self.audio_player.stop()
            if self.audio_player:
                self.audio_player.close()
                
            # Send robot to sleep
            if robot_base_url:
                try:
                    send_robot_command('z')  # Sleep command
                    print("DeskBot set to sleep mode")
                except:
                    print("DeskBot connection already closed")

        print("System shutdown complete")

    async def start_audio_recording(self) -> None:
        """Start recording audio from the microphone."""
        # Set up audio input stream
        self.audio_stream = sd.InputStream(
            channels=CHANNELS,
            samplerate=SAMPLE_RATE,
            dtype=FORMAT,
        )

        self.audio_stream.start()
        self.recording = True

        # Start audio capture task
        asyncio.create_task(self.capture_audio())

    async def capture_audio(self) -> None:
        """Capture audio from the microphone and send to the session."""
        if not self.audio_stream or not self.session:
            return

        # Buffer size in samples
        read_size = int(SAMPLE_RATE * CHUNK_LENGTH_S)

        try:
            while self.recording and robot_awake:
                # Check if there's enough data to read
                if self.audio_stream.read_available < read_size:
                    await asyncio.sleep(0.01)
                    continue

                # Read audio data
                data, _ = self.audio_stream.read(read_size)

                # Convert numpy array to bytes
                audio_bytes = data.tobytes()

                # Send audio to session
                await self.session.send_audio(audio_bytes)

                # Yield control back to event loop
                await asyncio.sleep(0)

        except Exception as e:
            print(f"Audio capture error: {e}")
        finally:
            if self.audio_stream and self.audio_stream.active:
                self.audio_stream.stop()
            if self.audio_stream:
                self.audio_stream.close()

    async def _on_event(self, event: RealtimeSessionEvent) -> None:
        """Handle session events."""
        try:
            if event.type == "agent_start":
                print(f"Agent started: {event.agent.name}")
            elif event.type == "agent_end":
                print(f"Agent ended: {event.agent.name}")
            elif event.type == "handoff":
                print(f"Handoff from {event.from_agent.name} to {event.to_agent.name}")
            elif event.type == "tool_start":
                print(f"Tool started: {event.tool.name}")
            elif event.type == "tool_end":
                print(f"Tool ended: {event.tool.name}; output: {event.output}")
            elif event.type == "audio_end":
                print("Audio ended")
            elif event.type == "audio":
                # Enqueue audio for callback-based playback
                np_audio = np.frombuffer(event.audio.data, dtype=np.int16)
                try:
                    self.output_queue.put_nowait(np_audio)
                except queue.Full:
                    if self.output_queue.qsize() > 8:
                        try:
                            self.output_queue.get_nowait()
                            self.output_queue.put_nowait(np_audio)
                        except queue.Empty:
                            pass
            elif event.type == "audio_interrupted":
                print("Audio interrupted")
                self.interrupt_event.set()
            elif event.type == "error":
                print(f"Error: {event.error}")
            elif event.type == "history_updated":
                pass  # Skip these frequent events
            elif event.type == "history_added":
                pass  # Skip these frequent events
            elif event.type == "raw_model_event":
                pass  # Skip verbose model events
            else:
                print(f"Unknown event type: {event.type}")
        except Exception as e:
            print(f"Error processing event: {e}")


if __name__ == "__main__":
    demo = NoUIDemo()
    try:
        asyncio.run(demo.run())
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit(0)
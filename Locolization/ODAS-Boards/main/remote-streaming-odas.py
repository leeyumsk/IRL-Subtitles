#!/usr/bin/env python3
import socket
import http.server
import socketserver
import threading
import numpy as np
import time
import argparse
import os
import subprocess
import queue
import struct
from typing import Tuple, List, Dict
import sounddevice as sd  # Using sounddevice instead of pyaudio for better I2S support

# Configuration constants
DEFAULT_SAMPLE_RATE = 48000  # ODAS typically works best with 48kHz
DEFAULT_BITS_PER_SAMPLE = 16
DEFAULT_PORT = 1234
DEFAULT_BUFFER_SIZE = 16384  # Buffer size for streaming
DEFAULT_CHUNK_SIZE = 1024    # Chunk size for audio processing
DEFAULT_ODAS_PORT = 10001    # Default UDP port for ODAS
DEFAULT_REMOTE_PORT = 10002  # Default port for remote audio streaming

# Global variables
stream_active = False
audio_buffer_a = bytearray(DEFAULT_BUFFER_SIZE * 2)  # *2 for 16-bit samples
audio_buffer_b = bytearray(DEFAULT_BUFFER_SIZE * 2)
buffer_a_pos = 0
buffer_b_pos = 0
buffer_sel = True
audio_stream = None
odas_queue = queue.Queue(maxsize=100)  # Queue for ODAS data
remote_queue = queue.Queue(maxsize=100)  # Queue for remote streaming data
odas_process = None
odas_socket = None
remote_socket = None
odas_enabled = False
remote_enabled = False
remote_host = None

def get_ip_address() -> str:
    """Get the IP address of the Raspberry Pi"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Doesn't need to be reachable
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def find_i2s_devices() -> Dict[int, Dict]:
    """Find and print available I2S audio input devices"""
    devices = sd.query_devices()
    device_info = {}
    
    print("\nAvailable audio input devices:")
    print("-" * 60)
    for i, dev in enumerate(devices):
        if dev['max_input_channels'] > 0:  # Input device
            print(f"Index: {i}, Name: {dev['name']}, Channels: {dev['max_input_channels']}")
            if 'i2s' in dev['name'].lower() or 'i2s' in dev['hostapi'].lower():
                print("  ↳ I2S DEVICE DETECTED")
            device_info[i] = {
                'index': i,
                'name': dev['name'],
                'maxInputChannels': dev['max_input_channels'],
                'hostapi': dev['hostapi'],
                'isI2S': 'i2s' in dev['name'].lower() or 'i2s' in dev['hostapi'].lower()
            }
    print("-" * 60)
    
    # Filter for I2S devices
    i2s_devices = {k: v for k, v in device_info.items() if v['isI2S']}
    
    if not i2s_devices:
        print("Warning: No I2S devices detected. If you have I2S microphones connected, they might be using a generic name.")
        print("Consider using devices with 'plughw' or 'hw' in their names if you're using ALSA on Linux.")
    
    return device_info

def start_odas_server(odas_port, odas_config=None):
    """Initialize and start ODAS server if config is provided, otherwise just initialize UDP socket"""
    global odas_process, odas_socket, odas_enabled
    
    # Create UDP socket for sending data to ODAS
    odas_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # If ODAS config is provided, start the ODAS process
    if odas_config:
        try:
            print(f"Starting ODAS with config: {odas_config}")
            odas_process = subprocess.Popen(
                ['odaslive', '-c', odas_config],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            print("ODAS process started")
            odas_enabled = True
            
            # Start thread to read output from ODAS
            odas_output_thread = threading.Thread(target=read_odas_output)
            odas_output_thread.daemon = True
            odas_output_thread.start()
            
        except Exception as e:
            print(f"Failed to start ODAS process: {e}")
            odas_enabled = False
    else:
        print(f"ODAS UDP streaming enabled on port {odas_port}")
        odas_enabled = True
    
    # Start thread to send data to ODAS
    odas_thread = threading.Thread(target=odas_stream_thread, args=(odas_port,))
    odas_thread.daemon = True
    odas_thread.start()

def start_remote_streaming(remote_host, remote_port):
    """Initialize and start remote streaming over UDP"""
    global remote_socket, remote_enabled
    
    if not remote_host:
        print("Remote streaming disabled: no remote host specified")
        return
    
    try:
        # Create UDP socket for sending data to remote host
        remote_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        remote_enabled = True
        
        print(f"Remote audio streaming enabled to {remote_host}:{remote_port}")
        
        # Start thread to send data to remote host
        remote_thread = threading.Thread(target=remote_stream_thread, args=(remote_host, remote_port))
        remote_thread.daemon = True
        remote_thread.start()
    except Exception as e:
        print(f"Failed to initialize remote streaming: {e}")
        remote_enabled = False

def read_odas_output():
    """Read and process output from ODAS process"""
    global odas_process
    
    while odas_process and odas_process.poll() is None:
        try:
            output = odas_process.stdout.readline()
            if output:
                print(f"ODAS: {output.decode('utf-8').strip()}")
        except Exception as e:
            print(f"Error reading ODAS output: {e}")
            time.sleep(0.1)

def odas_stream_thread(odas_port):
    """Thread that sends audio data to ODAS via UDP"""
    global odas_queue, odas_socket, odas_enabled
    
    while odas_enabled:
        try:
            # Get data from queue with timeout
            data = odas_queue.get(timeout=1.0)
            
            # Send to ODAS via UDP
            odas_socket.sendto(data, ('127.0.0.1', odas_port))
            
            # Mark task as done
            odas_queue.task_done()
        except queue.Empty:
            # No data available, just continue
            pass
        except Exception as e:
            print(f"Error in ODAS streaming: {e}")
            time.sleep(0.1)

def remote_stream_thread(remote_host, remote_port):
    """Thread that sends audio data to remote host via UDP"""
    global remote_queue, remote_socket, remote_enabled
    
    while remote_enabled:
        try:
            # Get data from queue with timeout
            data = remote_queue.get(timeout=1.0)
            
            # Send to remote host via UDP
            remote_socket.sendto(data, (remote_host, remote_port))
            
            # Mark task as done
            remote_queue.task_done()
            
        except queue.Empty:
            # No data available, just continue
            pass
        except Exception as e:
            print(f"Error in remote streaming: {e}")
            time.sleep(0.1)

def audio_callback(indata, frames, time_info, status):
    """Callback function for sounddevice stream"""
    global audio_buffer_a, audio_buffer_b, buffer_a_pos, buffer_b_pos, buffer_sel, odas_queue, odas_enabled, remote_queue, remote_enabled
    
    if status:
        print(f"Status: {status}")
    
    # Convert to int16 if needed
    if indata.dtype != np.int16:
        indata = (indata * 32767).astype(np.int16)
    
    # For a single I2S device with 4 channels, the data is already interleaved
    interleaved_bytes = indata.tobytes()
    
    # Send to ODAS if enabled
    if odas_enabled:
        try:
            # ODAS expects raw PCM data, so we send it directly
            if not odas_queue.full():
                odas_queue.put(interleaved_bytes)
        except Exception as e:
            print(f"Error sending data to ODAS: {e}")
    
    # Send to remote host if enabled
    if remote_enabled:
        try:
            # Send the same raw PCM data to remote host
            if not remote_queue.full():
                remote_queue.put(interleaved_bytes)
        except Exception as e:
            print(f"Error sending data to remote host: {e}")
    
    # Continue with HTTP streaming logic
    bytes_to_write = len(interleaved_bytes)
    
    # Write to the current buffer
    if buffer_sel:
        # Write to buffer A
        space_left = len(audio_buffer_a) - buffer_a_pos
        if bytes_to_write <= space_left:
            # We have enough space
            audio_buffer_a[buffer_a_pos:buffer_a_pos + bytes_to_write] = interleaved_bytes
            buffer_a_pos += bytes_to_write
            
            # Switch buffers if A is full
            if buffer_a_pos >= len(audio_buffer_a):
                buffer_sel = False
                buffer_a_pos = 0
        else:
            # Fill buffer A and switch to B for remainder
            audio_buffer_a[buffer_a_pos:] = interleaved_bytes[:space_left]
            buffer_sel = False
            buffer_a_pos = 0
            
            # Put remaining data in buffer B
            remaining = bytes_to_write - space_left
            if remaining > 0:
                audio_buffer_b[:remaining] = interleaved_bytes[space_left:]
                buffer_b_pos = remaining
    else:
        # Write to buffer B
        space_left = len(audio_buffer_b) - buffer_b_pos
        if bytes_to_write <= space_left:
            # We have enough space
            audio_buffer_b[buffer_b_pos:buffer_b_pos + bytes_to_write] = interleaved_bytes
            buffer_b_pos += bytes_to_write
            
            # Switch buffers if B is full
            if buffer_b_pos >= len(audio_buffer_b):
                buffer_sel = True
                buffer_b_pos = 0
        else:
            # Fill buffer B and switch to A for remainder
            audio_buffer_b[buffer_b_pos:] = interleaved_bytes[:space_left]
            buffer_sel = True
            buffer_b_pos = 0
            
            # Put remaining data in buffer A
            remaining = bytes_to_write - space_left
            if remaining > 0:
                audio_buffer_a[:remaining] = interleaved_bytes[space_left:]
                buffer_a_pos = remaining

def setup_i2s_stream(device_index: int, sample_rate: int, channels: int, chunk_size: int) -> bool:
    """Set up I2S audio input stream"""
    global audio_stream, stream_active
    
    try:
        print(f"Opening I2S device {device_index} with {channels} channels at {sample_rate} Hz")
        
        # Create the audio stream
        audio_stream = sd.InputStream(
            device=device_index,
            channels=channels,
            samplerate=sample_rate,
            blocksize=chunk_size,
            dtype='int16',
            callback=audio_callback
        )
        
        # Start the stream
        audio_stream.start()
        stream_active = True
        
        print(f"Started I2S audio stream with {channels} channels at {sample_rate} Hz")
        return True
        
    except Exception as e:
        print(f"Error opening I2S device {device_index}: {e}")
        return False

class AudioStreamHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for audio streaming"""
    
    def do_GET(self):
        global buffer_sel, audio_buffer_a, audio_buffer_b, stream_active, odas_enabled, remote_enabled, remote_host
        
        if self.path == '/ach1':
            self.send_response(200)
            self.send_header('Content-type', 'audio/raw')
            self.send_header('X-Audio-Sample-Rate', str(DEFAULT_SAMPLE_RATE))
            self.send_header('X-Audio-Bits-Per-Sample', str(DEFAULT_BITS_PER_SAMPLE))
            self.send_header('X-Audio-Channels', '4')  # 4 channels
            self.send_header('Connection', 'keep-alive')
            self.end_headers()
            
            print(f"Client connected from {self.client_address}")
            client_buffer_sel = not buffer_sel  # Use opposite buffer from what's being filled
            last_buffer_sel = client_buffer_sel
            
            try:
                while stream_active:
                    # If the current buffer selection changed, we're ready to send new data
                    if client_buffer_sel != last_buffer_sel:
                        if client_buffer_sel:
                            # Send buffer A
                            self.wfile.write(bytes(audio_buffer_a))
                        else:
                            # Send buffer B
                            self.wfile.write(bytes(audio_buffer_b))
                        
                        # Update the last buffer selection
                        last_buffer_sel = client_buffer_sel
                    
                    # Update our buffer selection (opposite of what's being filled)
                    client_buffer_sel = not buffer_sel
                    
                    # Short sleep to prevent CPU hogging
                    time.sleep(0.001)
                    
            except (BrokenPipeError, ConnectionResetError) as e:
                print(f"Client disconnected: {e}")
            except Exception as e:
                print(f"Error during streaming: {e}")
                
        elif self.path == '/':
            # Serve a simple HTML page with streaming info
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Raspberry Pi 4-Mic I2S Audio Streamer with ODAS</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    h1 {{ color: #333; }}
                    .info {{ background-color: #f0f0f0; padding: 10px; border-radius: 5px; }}
                    .status {{ font-weight: bold; }}
                    .enabled {{ color: green; }}
                    .disabled {{ color: red; }}
                </style>
            </head>
            <body>
                <h1>Raspberry Pi 4-Mic I2S Audio Streamer with ODAS</h1>
                <div class="info">
                    <p>Streaming 4-channel I2S audio at {DEFAULT_SAMPLE_RATE} Hz</p>
                    <p>I2S microphone array: <span class="status enabled">Active</span></p>
                    <p>ODAS integration: <span class="status {'enabled' if odas_enabled else 'disabled'}">{'Enabled' if odas_enabled else 'Disabled'}</span></p>
                    <p>Remote streaming: <span class="status {'enabled' if remote_enabled else 'disabled'}">{'Enabled to ' + remote_host if remote_enabled else 'Disabled'}</span></p>
                    <p>Access the raw audio stream at: <a href="/ach1">/ach1</a></p>
                </div>
            </body>
            </html>
            """
            
            self.wfile.write(html.encode())
                
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not found')

def run_server(port):
    """Run the HTTP server on the specified port"""
    # Create a custom server that allows for quick rebinding
    server = socketserver.TCPServer(("", port), AudioStreamHandler, bind_and_activate=False)
    server.allow_reuse_address = True
    server.server_bind()
    server.server_activate()
    
    print(f"Server started on http://{get_ip_address()}:{port}/")
    print(f"Audio stream available at http://{get_ip_address()}:{port}/ach1")
    print("Press Ctrl+C to stop")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

def main():
    """Main function to run the audio streaming server"""
    global stream_active, audio_stream, odas_process, odas_enabled, remote_enabled, remote_host
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Raspberry Pi 4-Mic I2S Audio Streaming Server with ODAS and Remote Streaming')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help='HTTP server port')
    parser.add_argument('--sample-rate', type=int, default=DEFAULT_SAMPLE_RATE, help='Audio sample rate in Hz')
    parser.add_argument('--buffer-size', type=int, default=DEFAULT_BUFFER_SIZE, help='Audio buffer size')
    parser.add_argument('--chunk-size', type=int, default=DEFAULT_CHUNK_SIZE, help='Audio processing chunk size')
    parser.add_argument('--device', type=int, help='I2S device index')
    parser.add_argument('--channels', type=int, default=4, help='Number of channels (4 for quad mic array)')
    parser.add_argument('--list-devices', action='store_true', help='List available audio devices and exit')
    parser.add_argument('--odas-port', type=int, default=DEFAULT_ODAS_PORT, help='UDP port for ODAS')
    parser.add_argument('--odas-config', type=str, help='Path to ODAS configuration file (if provided, odaslive will be launched)')
    parser.add_argument('--no-odas', action='store_true', help='Disable ODAS integration')
    parser.add_argument('--remote-host', type=str, help='IP address or hostname of remote computer for audio streaming')
    parser.add_argument('--remote-port', type=int, default=DEFAULT_REMOTE_PORT, help='UDP port for remote audio streaming')
    
    args = parser.parse_args()
    
    # Store remote host for use in HTML status
    remote_host = args.remote_host
    
    try:
        # List devices if requested
        if args.list_devices:
            find_i2s_devices()
            return
        
        # Find available I2S input devices
        device_info = find_i2s_devices()
        
        if not device_info:
            print("No audio input devices found!")
            return
        
        # Determine which device to use
        device_index = None
        
        if args.device is not None:
            # Use device specified by the user
            device_index = args.device
            print(f"Using user-specified device: {device_index}")
        else:
            # Auto-select the first I2S device, or first device if no I2S device is found
            i2s_devices = [idx for idx, info in device_info.items() if info.get('isI2S', False)]
            if i2s_devices:
                device_index = i2s_devices[0]
                print(f"Auto-selected I2S device: {device_index}")
            else:
                device_index = list(device_info.keys())[0]
                print(f"No I2S device found. Auto-selected device: {device_index}")
        
        # Setup the I2S audio stream
        if not setup_i2s_stream(device_index, args.sample_rate, args.channels, args.chunk_size):
            print("Failed to set up I2S audio stream. Exiting.")
            return
        
        # Initialize ODAS if not disabled
        if not args.no_odas:
            start_odas_server(args.odas_port, args.odas_config)
        
        # Initialize remote streaming if host is provided
        if args.remote_host:
            start_remote_streaming(args.remote_host, args.remote_port)
        
        # Start the HTTP server
        run_server(args.port)
            
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        # Clean up
        stream_active = False
        odas_enabled = False
        remote_enabled = False
        time.sleep(0.5)  # Give time for threads to clean up
        
        # Close audio stream
        if audio_stream:
            audio_stream.stop()
            audio_stream.close()
        
        # Terminate ODAS process if running
        if odas_process and odas_process.poll() is None:
            print("Terminating ODAS process...")
            odas_process.terminate()
            odas_process.wait(timeout=5)

if __name__ == "__main__":
    main()

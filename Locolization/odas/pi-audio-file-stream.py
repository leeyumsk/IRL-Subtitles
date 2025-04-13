#!/usr/bin/env python3
import socket
import http.server
import socketserver
import threading
import numpy as np
import time
import argparse
import os
from typing import Tuple, List

# Configuration constants
DEFAULT_SAMPLE_RATE = 24000
DEFAULT_CHANNELS = 4  # 4 channels
DEFAULT_BITS_PER_SAMPLE = 16
DEFAULT_PORT = 1234
DEFAULT_BUFFER_SIZE = 16384  # Similar to ESP32 buffer size
DEFAULT_AUDIO_FILE = "audio.raw"  # Default raw audio file

# Global variables
stream_active = False
audio_buffer_a = bytearray(DEFAULT_BUFFER_SIZE * 2)  # *2 for 16-bit samples
audio_buffer_b = bytearray(DEFAULT_BUFFER_SIZE * 2)
buffer_sel = True
file_data = None
file_position = 0

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

def load_audio_file(file_path: str, buffer_size: int) -> bytes:
    """Load the audio file into memory"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")
    
    print(f"Loading audio file: {file_path}")
    with open(file_path, 'rb') as f:
        audio_data = f.read()
    
    # Check if file is of reasonable size
    file_size_mb = len(audio_data) / (1024 * 1024)
    print(f"Audio file size: {file_size_mb:.2f} MB")
    print(f"Duration: ~{len(audio_data) / (DEFAULT_SAMPLE_RATE * DEFAULT_CHANNELS * 2):.2f} seconds " +
          f"(at {DEFAULT_SAMPLE_RATE} Hz, {DEFAULT_CHANNELS} channels, 16-bit)")
    
    return audio_data

def fill_buffers(audio_data: bytes) -> None:
    """Start a thread to continuously fill the audio buffers from the file data"""
    global stream_active, buffer_sel, audio_buffer_a, audio_buffer_b, file_position
    
    def buffer_filler():
        global stream_active, buffer_sel, audio_buffer_a, audio_buffer_b, file_position
        
        while stream_active:
            # Fill the inactive buffer while the active one is being streamed
            target_buffer = audio_buffer_a if buffer_sel else audio_buffer_b
            
            # Fill buffer with data, looping the file as needed
            bytes_to_copy = len(target_buffer)
            remaining_bytes = len(audio_data) - file_position
            
            if remaining_bytes >= bytes_to_copy:
                # We have enough data to fill the buffer
                target_buffer[:] = audio_data[file_position:file_position + bytes_to_copy]
                file_position += bytes_to_copy
            else:
                # We need to wrap around to the beginning of the file
                target_buffer[:remaining_bytes] = audio_data[file_position:]
                target_buffer[remaining_bytes:] = audio_data[:bytes_to_copy - remaining_bytes]
                file_position = bytes_to_copy - remaining_bytes
                print(f"Audio file looped at position {file_position}")
            
            # Sleep a bit to prevent CPU hogging
            time.sleep(0.01)
    
    # Reset file position
    file_position = 0
    
    # Start the buffer filler thread
    filler_thread = threading.Thread(target=buffer_filler)
    filler_thread.daemon = True
    filler_thread.start()

class AudioStreamHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for audio streaming"""
    
    def do_GET(self):
        global buffer_sel, audio_buffer_a, audio_buffer_b, stream_active
        
        if self.path == '/ach1':
            self.send_response(200)
            self.send_header('Content-type', 'audio/raw')
            self.send_header('X-Audio-Sample-Rate', str(DEFAULT_SAMPLE_RATE))
            self.send_header('X-Audio-Bits-Per-Sample', str(DEFAULT_BITS_PER_SAMPLE))
            self.send_header('X-Audio-Channels', str(DEFAULT_CHANNELS))
            self.send_header('Connection', 'keep-alive')
            self.end_headers()
            
            print(f"Client connected from {self.client_address}")
            
            try:
                while stream_active:
                    # Toggle buffers and send the currently filled one
                    if buffer_sel:
                        # Use buffer B for sending, A is being filled
                        self.wfile.write(audio_buffer_b)
                        buffer_sel = False
                    else:
                        # Use buffer A for sending, B is being filled
                        self.wfile.write(audio_buffer_a)
                        buffer_sel = True
                    
                    # Simulate the timing of real-time audio
                    # Buffer size in bytes / (sample rate * channels * bytes per sample)
                    buffer_duration = len(audio_buffer_a) / (DEFAULT_SAMPLE_RATE * DEFAULT_CHANNELS * 2)
                    time.sleep(buffer_duration * 0.8)  # Sleep slightly less than buffer duration to ensure smooth playback
                    
            except (BrokenPipeError, ConnectionResetError) as e:
                print(f"Client disconnected: {e}")
            except Exception as e:
                print(f"Error during streaming: {e}")
        
        elif self.path == '/':
            # Serve a simple HTML page with an audio player
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Raspberry Pi Audio Streamer</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    h1 {{ color: #333; }}
                    .info {{ background-color: #f0f0f0; padding: 10px; border-radius: 5px; }}
                </style>
            </head>
            <body>
                <h1>Raspberry Pi Audio Streamer</h1>
                <div class="info">
                    <p>Streaming 4-channel raw audio at {DEFAULT_SAMPLE_RATE} Hz</p>
                    <p>Access the raw audio stream at: <a href="/ach1">/ach1</a></p>
                    <p>Note: Direct playback in browser is not supported for raw audio. Use a compatible client.</p>
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
    global stream_active, file_data
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Raspberry Pi Audio File Streaming Server')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help='HTTP server port')
    parser.add_argument('--sample-rate', type=int, default=DEFAULT_SAMPLE_RATE, 
                       help='Audio sample rate in Hz (should match the file)')
    parser.add_argument('--buffer-size', type=int, default=DEFAULT_BUFFER_SIZE, help='Audio buffer size')
    parser.add_argument('--file', type=str, default=DEFAULT_AUDIO_FILE, 
                       help='Path to the raw audio file to stream')
    
    args = parser.parse_args()
    
    try:
        # Load the audio file
        file_data = load_audio_file(args.file, args.buffer_size)
        
        # Set active flag
        stream_active = True
        
        # Start buffer filling
        fill_buffers(file_data)
        
        # Start the HTTP server
        run_server(args.port)
            
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print(f"Please provide a valid raw audio file with {DEFAULT_CHANNELS} channels at {DEFAULT_SAMPLE_RATE} Hz")
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        stream_active = False
        time.sleep(0.5)  # Give time for threads to clean up

if __name__ == "__main__":
    main()

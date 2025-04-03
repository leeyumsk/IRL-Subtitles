#!/usr/bin/env python3
import pyaudio
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
DEFAULT_CHANNELS_PER_MIC = 2  # Stereo
DEFAULT_BITS_PER_SAMPLE = 16
DEFAULT_PORT = 1234
DEFAULT_BUFFER_SIZE = 16384  # Similar to ESP32 buffer size (8192 * 2)
DEVICE_INDEX_1 = None  # Will be detected
DEVICE_INDEX_2 = None  # Will be detected

# Global variables
stream_active = False
audio_buffer_a = bytearray(DEFAULT_BUFFER_SIZE * 2)  # *2 for 16-bit samples
audio_buffer_b = bytearray(DEFAULT_BUFFER_SIZE * 2)
buffer_sel = True
audio = None

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

def find_audio_devices() -> Tuple[List[int], List[str]]:
    """Find and print available audio devices, return lists of indices and names"""
    global audio
    
    if audio is None:
        audio = pyaudio.PyAudio()
    
    device_indices = []
    device_names = []
    
    print("\nAvailable audio input devices:")
    print("-" * 60)
    for i in range(audio.get_device_count()):
        dev_info = audio.get_device_info_by_index(i)
        if dev_info['maxInputChannels'] > 0:  # Input device
            print(f"Index: {i}, Name: {dev_info['name']}, Channels: {dev_info['maxInputChannels']}")
            device_indices.append(i)
            device_names.append(dev_info['name'])
    print("-" * 60)
    
    return device_indices, device_names

def setup_audio_stream(device_index_1: int, device_index_2: int, sample_rate: int, 
                      channels_per_mic: int, buffer_size: int) -> None:
    """Set up the dual audio input stream"""
    global audio, buffer_sel, audio_buffer_a, audio_buffer_b, stream_active
    
    if audio is None:
        audio = pyaudio.PyAudio()
    
    buffer_index_a = 0
    buffer_index_b = 0
    
    def audio_callback(in_data, frame_count, time_info, status):
        nonlocal buffer_index_a, buffer_index_b
        
        if not stream_active:
            return (None, pyaudio.paComplete)
        
        # Convert input data to numpy array for processing
        # Format is typically interleaved already in PyAudio
        audio_data = np.frombuffer(in_data, dtype=np.int16)
        
        # If we're using two separate devices, we need to interleave them manually
        # Otherwise, PyAudio is already giving us interleaved data from a single device
        
        # Copy the data to the appropriate buffer
        if buffer_sel:
            bytes_to_copy = min(len(audio_data) * 2, len(audio_buffer_a) - buffer_index_a)
            if bytes_to_copy > 0:
                audio_buffer_a[buffer_index_a:buffer_index_a + bytes_to_copy] = audio_data.tobytes()[:bytes_to_copy]
                buffer_index_a += bytes_to_copy
                
                if buffer_index_a >= len(audio_buffer_a):
                    buffer_index_a = 0
                    buffer_sel = False  # Switch to buffer B
        else:
            bytes_to_copy = min(len(audio_data) * 2, len(audio_buffer_b) - buffer_index_b)
            if bytes_to_copy > 0:
                audio_buffer_b[buffer_index_b:buffer_index_b + bytes_to_copy] = audio_data.tobytes()[:bytes_to_copy]
                buffer_index_b += bytes_to_copy
                
                if buffer_index_b >= len(audio_buffer_b):
                    buffer_index_b = 0
                    buffer_sel = True  # Switch to buffer A
        
        return (None, pyaudio.paContinue)
    
    # Initialize streams based on device configuration
    if device_index_1 == device_index_2:
        # Single device with multiple channels
        print(f"Opening single audio device (index {device_index_1}) with {channels_per_mic * 2} channels")
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=channels_per_mic * 2,  # Total channels (2 mics × channels per mic)
            rate=sample_rate,
            input=True,
            input_device_index=device_index_1,
            frames_per_buffer=buffer_size // 4,  # Adjust for 16-bit samples and channel count
            stream_callback=audio_callback
        )
    else:
        # Two separate devices that we'll need to combine
        # This setup is more complex and would require modification
        # to properly interleave two separate audio streams
        print(f"Opening two audio devices (indices {device_index_1} and {device_index_2})")
        print("WARNING: Dual device mode requires additional implementation for proper interleaving")
        
        # For demonstration, we'll just open the first device
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=channels_per_mic * 2,  # Total channels
            rate=sample_rate,
            input=True,
            input_device_index=device_index_1,
            frames_per_buffer=buffer_size // 4,
            stream_callback=audio_callback
        )
    
    stream_active = True
    print(f"Audio stream started at {sample_rate} Hz, {DEFAULT_BITS_PER_SAMPLE} bits, {channels_per_mic * 2} channels")
    
    return stream

class AudioStreamHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for audio streaming"""
    
    def do_GET(self):
        global buffer_sel, audio_buffer_a, audio_buffer_b, stream_active
        
        if self.path == '/ach1':
            self.send_response(200)
            self.send_header('Content-type', 'audio/raw')
            self.send_header('X-Audio-Sample-Rate', str(DEFAULT_SAMPLE_RATE))
            self.send_header('X-Audio-Bits-Per-Sample', str(DEFAULT_BITS_PER_SAMPLE))
            self.send_header('X-Audio-Channels', '4')  # 4 channels total (2 stereo mics)
            self.send_header('Connection', 'keep-alive')
            self.end_headers()
            
            print(f"Client connected from {self.client_address}")
            
            try:
                while stream_active:
                    if buffer_sel:
                        self.wfile.write(audio_buffer_b)
                    else:
                        self.wfile.write(audio_buffer_a)
                    
                    # Small delay to prevent busy-waiting
                    time.sleep(0.001)
                    
            except (BrokenPipeError, ConnectionResetError) as e:
                print(f"Client disconnected: {e}")
            except Exception as e:
                print(f"Error during streaming: {e}")
                
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
    
    print(f"Server started on http://{get_ip_address()}:{port}/ach1")
    print("Press Ctrl+C to stop")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

def main():
    """Main function to run the audio streaming server"""
    global DEVICE_INDEX_1, DEVICE_INDEX_2, stream_active, audio
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Raspberry Pi Audio Streaming Server')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help='HTTP server port')
    parser.add_argument('--sample-rate', type=int, default=DEFAULT_SAMPLE_RATE, help='Audio sample rate in Hz')
    parser.add_argument('--buffer-size', type=int, default=DEFAULT_BUFFER_SIZE, help='Audio buffer size')
    parser.add_argument('--device1', type=int, help='Audio device index for first microphone')
    parser.add_argument('--device2', type=int, help='Audio device index for second microphone (optional)')
    parser.add_argument('--channels', type=int, default=DEFAULT_CHANNELS_PER_MIC, 
                        help='Number of channels per microphone (usually 1 or 2)')
    parser.add_argument('--list-devices', action='store_true', help='List available audio devices and exit')
    
    args = parser.parse_args()
    
    # Initialize PyAudio
    audio = pyaudio.PyAudio()
    
    try:
        # List devices if requested
        if args.list_devices:
            find_audio_devices()
            return
        
        # Find and select audio devices
        device_indices, device_names = find_audio_devices()
        
        if not device_indices:
            print("No audio input devices found!")
            return
        
        # Set device indices based on arguments or defaults
        if args.device1 is not None:
            DEVICE_INDEX_1 = args.device1
        else:
            DEVICE_INDEX_1 = device_indices[0]  # Use first available device by default
            
        if args.device2 is not None:
            DEVICE_INDEX_2 = args.device2
        else:
            DEVICE_INDEX_2 = DEVICE_INDEX_1  # Use same device by default
            
        print(f"Using device(s): {DEVICE_INDEX_1}" + 
              (f", {DEVICE_INDEX_2}" if DEVICE_INDEX_2 != DEVICE_INDEX_1 else " (for both streams)"))
        
        # Setup the audio stream
        stream = setup_audio_stream(
            DEVICE_INDEX_1,
            DEVICE_INDEX_2,
            args.sample_rate,
            args.channels,
            args.buffer_size
        )
        
        # Start the HTTP server in a separate thread
        server_thread = threading.Thread(target=run_server, args=(args.port,))
        server_thread.daemon = True
        server_thread.start()
        
        # Keep the main thread running to handle keyboard interrupts
        try:
            while server_thread.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down...")
            stream_active = False
            time.sleep(0.5)  # Give time for threads to clean up
            
    finally:
        if audio:
            audio.terminate()

if __name__ == "__main__":
    main()

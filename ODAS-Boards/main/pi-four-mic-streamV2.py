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
from typing import Tuple, List, Dict

# Configuration constants
DEFAULT_SAMPLE_RATE = 24000
DEFAULT_BITS_PER_SAMPLE = 16
DEFAULT_PORT = 1234
DEFAULT_BUFFER_SIZE = 16384  # Buffer size for streaming
DEFAULT_CHUNK_SIZE = 1024    # Chunk size for PyAudio processing

# Global variables
stream_active = False
audio_buffer_a = bytearray(DEFAULT_BUFFER_SIZE * 2)  # *2 for 16-bit samples
audio_buffer_b = bytearray(DEFAULT_BUFFER_SIZE * 2)
buffer_a_pos = 0
buffer_b_pos = 0
buffer_sel = True
audio = None
streams = []

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

def find_audio_devices() -> Dict[int, Dict]:
    """Find and print available audio input devices, return dict of indices and info"""
    global audio
    
    if audio is None:
        audio = pyaudio.PyAudio()
    
    device_info = {}
    
    print("\nAvailable audio input devices:")
    print("-" * 60)
    for i in range(audio.get_device_count()):
        dev_info = audio.get_device_info_by_index(i)
        if dev_info['maxInputChannels'] > 0:  # Input device
            print(f"Index: {i}, Name: {dev_info['name']}, Channels: {dev_info['maxInputChannels']}")
            device_info[i] = dev_info
    print("-" * 60)
    
    return device_info

def setup_audio_streams(device_indices: List[int], sample_rate: int, chunk_size: int) -> bool:
    """Set up multiple audio input streams from different devices"""
    global audio, streams, stream_active
    
    if audio is None:
        audio = pyaudio.PyAudio()
    
    if len(device_indices) == 0:
        print("Error: No input devices specified!")
        return False
    
    # Initialize buffer processor thread
    buffer_thread = threading.Thread(target=process_audio_buffers)
    buffer_thread.daemon = True
    
    # Create separate streams for each microphone
    for idx, device_index in enumerate(device_indices):
        try:
            print(f"Opening device {device_index} as microphone {idx+1}")
            
            # Get device info to confirm it's available
            try:
                info = audio.get_device_info_by_index(device_index)
                print(f"Device info: {info['name']}, Max input channels: {info['maxInputChannels']}")
            except Exception as e:
                print(f"Error getting device info: {e}")
                continue
            
            # Create the audio stream
            stream = audio.open(
                format=pyaudio.paInt16,
                channels=1,  # Mono for each mic
                rate=sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=chunk_size,
                start=False  # Don't start yet
            )
            
            streams.append({
                'stream': stream,
                'device_index': device_index,
                'mic_number': idx + 1
            })
            
        except Exception as e:
            print(f"Error opening device {device_index}: {e}")
    
    if len(streams) == 0:
        print("Failed to open any audio streams!")
        return False
    
    # Start all streams
    for stream_info in streams:
        stream_info['stream'].start_stream()
    
    # Start buffer processing thread
    stream_active = True
    buffer_thread.start()
    
    print(f"Started {len(streams)} audio streams at {sample_rate} Hz")
    return True

def process_audio_buffers():
    """Read from all streams and interleave the data into our buffers"""
    global streams, audio_buffer_a, audio_buffer_b, buffer_a_pos, buffer_b_pos, buffer_sel, stream_active
    
    chunk_size = DEFAULT_CHUNK_SIZE
    
    while stream_active:
        try:
            # Read from all streams
            chunks = []
            for stream_info in streams:
                data = stream_info['stream'].read(chunk_size, exception_on_overflow=False)
                chunks.append(np.frombuffer(data, dtype=np.int16))
            
            # If we don't have 4 microphones, pad with zeros
            while len(chunks) < 4:
                chunks.append(np.zeros(chunk_size, dtype=np.int16))
            
            # If we have more than 4, truncate
            chunks = chunks[:4]
            
            # Interleave the samples from all microphones
            interleaved = np.empty(chunk_size * 4, dtype=np.int16)
            for i in range(chunk_size):
                for mic in range(4):
                    interleaved[i*4 + mic] = chunks[mic][i]
            
            # Convert to bytes
            interleaved_bytes = interleaved.tobytes()
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
            
        except Exception as e:
            print(f"Error processing audio: {e}")
            time.sleep(0.1)  # Avoid tight loop on error

class AudioStreamHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for audio streaming"""
    
    def do_GET(self):
        global buffer_sel, audio_buffer_a, audio_buffer_b, stream_active
        
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
                <title>Raspberry Pi 4-Mic Audio Streamer</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    h1 {{ color: #333; }}
                    .info {{ background-color: #f0f0f0; padding: 10px; border-radius: 5px; }}
                </style>
            </head>
            <body>
                <h1>Raspberry Pi 4-Mic Audio Streamer</h1>
                <div class="info">
                    <p>Streaming 4-channel audio at {DEFAULT_SAMPLE_RATE} Hz</p>
                    <p>Microphones active: {len(streams)}</p>
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
    global stream_active, audio, streams
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Raspberry Pi 4-Mic Audio Streaming Server')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help='HTTP server port')
    parser.add_argument('--sample-rate', type=int, default=DEFAULT_SAMPLE_RATE, help='Audio sample rate in Hz')
    parser.add_argument('--buffer-size', type=int, default=DEFAULT_BUFFER_SIZE, help='Audio buffer size')
    parser.add_argument('--chunk-size', type=int, default=DEFAULT_CHUNK_SIZE, help='Audio processing chunk size')
    parser.add_argument('--devices', type=int, nargs='+', help='Audio device indices for microphones (up to 4)')
    parser.add_argument('--list-devices', action='store_true', help='List available audio devices and exit')
    
    args = parser.parse_args()
    
    # Initialize PyAudio
    audio = pyaudio.PyAudio()
    
    try:
        # List devices if requested
        if args.list_devices:
            find_audio_devices()
            return
        
        # Find available input devices
        device_info = find_audio_devices()
        
        if not device_info:
            print("No audio input devices found!")
            return
        
        # Determine which devices to use
        device_indices = []
        
        if args.devices:
            # Use devices specified by the user
            device_indices = args.devices
            print(f"Using user-specified devices: {device_indices}")
        else:
            # Auto-select devices
            device_indices = list(device_info.keys())[:4]
            print(f"Auto-selected devices: {device_indices}")
        
        # Limit to 4 devices
        device_indices = device_indices[:4]
        
        # Setup the audio streams
        if not setup_audio_streams(device_indices, args.sample_rate, args.chunk_size):
            print("Failed to set up audio streams. Exiting.")
            return
        
        # Start the HTTP server
        run_server(args.port)
            
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        # Clean up
        stream_active = False
        time.sleep(0.5)  # Give time for threads to clean up
        
        # Close all streams
        for stream_info in streams:
            if stream_info['stream'].is_active():
                stream_info['stream'].stop_stream()
            stream_info['stream'].close()
        
        # Terminate PyAudio
        if audio:
            audio.terminate()

if __name__ == "__main__":
    main()

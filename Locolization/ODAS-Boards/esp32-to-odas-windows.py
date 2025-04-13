#!/usr/bin/env python3
import socket
import struct
import wave
import argparse
import time
from threading import Thread
import queue
import os

class ESP32AudioStreamConverter:
    def __init__(self, esp32_ip="192.168.4.254", esp32_port=80, esp32_path="/ach1",
                 odas_host="172.28.16.1", odas_port=1001, buffer_size=16384, channels=4,
                 sample_rate=24000, bits_per_sample=16, save_wav=False, server_mode=False):
        """
        Initialize the converter to transform ESP32 audio stream to ODAS input format.
        
        Args:
            esp32_ip: IP address of the ESP32 device
            esp32_port: HTTP port of the ESP32 server
            esp32_path: Path to the audio stream endpoint
            odas_host: ODAS server hostname or IP
            odas_port: ODAS raw audio input port
            buffer_size: Size of audio buffer
            channels: Number of audio channels
            sample_rate: Audio sample rate in Hz
            bits_per_sample: Bits per audio sample
            save_wav: Whether to save received audio to WAV file
            server_mode: True to listen for ODAS connection, False to connect to ODAS
        """
        self.esp32_ip = esp32_ip
        self.esp32_port = esp32_port
        self.esp32_path = esp32_path
        self.odas_host = odas_host
        self.odas_port = odas_port
        self.buffer_size = buffer_size
        self.channels = channels
        self.sample_rate = sample_rate
        self.bits_per_sample = bits_per_sample
        self.bytes_per_sample = bits_per_sample // 8
        self.save_wav = save_wav
        self.server_mode = server_mode
        self.running = False
        self.audio_queue = queue.Queue(maxsize=10)
        
        if save_wav:
            self.wav_filename = f"esp32_audio_{int(time.time())}.wav"
            self.wav_file = wave.open(self.wav_filename, "wb")
            self.wav_file.setnchannels(channels)
            self.wav_file.setsampwidth(self.bytes_per_sample)
            self.wav_file.setframerate(sample_rate)
            print(f"Saving audio to {self.wav_filename}")
    
    def _connect_to_esp32(self):
        """Establish HTTP connection to ESP32 server and request audio stream."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10)  # Add timeout to avoid hanging forever
        
        try:
            print(f"Connecting to ESP32 at {self.esp32_ip}:{self.esp32_port}{self.esp32_path}...")
            s.connect((self.esp32_ip, self.esp32_port))
            
            # Send HTTP GET request for audio stream
            request = f"GET {self.esp32_path} HTTP/1.1\r\nHost: {self.esp32_ip}\r\nConnection: keep-alive\r\n\r\n"
            s.sendall(request.encode())

            # Skip HTTP headers until we find empty line
            print("Waiting for HTTP response headers...")
            buffer = b''
            while True:
                chunk = s.recv(1024)
                if not chunk:
                    raise ConnectionError("Connection closed before headers completed")
                
                buffer += chunk
                if b'\r\n\r\n' in buffer:
                    print("Found end of headers")
                    # Keep any audio data that came after headers
                    _, audio_data = buffer.split(b'\r\n\r\n', 1)
                    if audio_data:
                        self.audio_queue.put(audio_data)
                    break
            
            print(f"Connected to ESP32 audio stream at {self.esp32_ip}:{self.esp32_port}")
            return s
        except socket.timeout:
            print("Connection to ESP32 timed out. Is the ESP32 powered on and accessible?")
            raise
        except socket.error as e:
            print(f"Socket error connecting to ESP32: {e}")
            raise
    
    def _setup_odas_server(self):
        """Set up a server to wait for ODAS to connect."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            # Bind to any available address
            s.bind(('0.0.0.0', self.odas_port))
            s.listen(1)
            print(f"Waiting for ODAS to connect on port {self.odas_port}...")
            
            # Accept connection from ODAS
            client_socket, client_address = s.accept()
            print(f"ODAS connected from {client_address}")
            
            return client_socket, s
        except socket.error as e:
            print(f"Socket error setting up ODAS server: {e}")
            s.close()
            raise
    
    def _connect_to_odas(self):
        """Establish socket connection to ODAS server."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10)  # Add timeout to avoid hanging forever
        
        retry_count = 0
        max_retries = 5
        retry_delay = 2  # seconds
        
        while retry_count < max_retries:
            try:
                print(f"Connecting to ODAS at {self.odas_host}:{self.odas_port}...")
                s.connect((self.odas_host, self.odas_port))
                print(f"Successfully connected to ODAS at {self.odas_host}:{self.odas_port}")
                return s
            except socket.error as e:
                retry_count += 1
                print(f"Attempt {retry_count}/{max_retries}: Failed to connect to ODAS: {e}")
                if retry_count < max_retries:
                    print(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    print("Max retry attempts reached. Is ODAS running and listening on the correct port?")
                    raise
        
    def _receive_audio_thread(self):
        """Thread function for receiving audio from ESP32."""
        esp32_socket = None
        
        try:
            esp32_socket = self._connect_to_esp32()
            
            while self.running:
                # Read audio data from ESP32
                try:
                    raw_data = esp32_socket.recv(self.buffer_size)
                    if not raw_data:
                        print("Connection closed by ESP32")
                        break
                    
                    # print(f"Received {len(raw_data)} bytes from ESP32")
                    self.audio_queue.put(raw_data)
                    
                    if self.save_wav:
                        self.wav_file.writeframes(raw_data)
                except socket.error as e:
                    print(f"Socket error while receiving audio: {e}")
                    break
                    
        except Exception as e:
            print(f"Error in receive audio thread: {str(e)}")
        finally:
            if esp32_socket:
                esp32_socket.close()
                print("ESP32 connection closed")
            self.running = False
    
    def _process_audio_thread(self):
        """Thread function for processing audio and forwarding to ODAS."""
        odas_socket = None
        server_socket = None
        
        try:
            if self.server_mode:
                odas_socket, server_socket = self._setup_odas_server()
            else:
                odas_socket = self._connect_to_odas()
            
            bytes_sent = 0
            while self.running:
                try:
                    # Get audio data from queue with timeout
                    raw_data = self.audio_queue.get(timeout=1.0)
                    
                    # Forward to ODAS
                    odas_socket.sendall(raw_data)
                    bytes_sent += len(raw_data)
                    if bytes_sent >= 1000000:  # Log every ~1MB
                        print(f"Sent {bytes_sent/1000000:.2f}MB to ODAS")
                        bytes_sent = 0
                    
                    self.audio_queue.task_done()
                    
                except queue.Empty:
                    continue
                except socket.error as e:
                    print(f"Socket error sending to ODAS: {e}")
                    break
                    
        except Exception as e:
            print(f"Error in process audio thread: {str(e)}")
        finally:
            if odas_socket:
                odas_socket.close()
                print("ODAS connection closed")
            if server_socket:
                server_socket.close()
                print("ODAS server socket closed")
            self.running = False
    
    def start(self):
        """Start the converter."""
        self.running = True
        
        # Start receiver thread
        self.receiver_thread = Thread(target=self._receive_audio_thread)
        self.receiver_thread.daemon = True
        self.receiver_thread.start()
        
        # Start processor thread
        self.processor_thread = Thread(target=self._process_audio_thread)
        self.processor_thread.daemon = True
        self.processor_thread.start()
        
        print("Converter started")
        
        try:
            # Keep main thread alive and display status
            while self.running:
                print(f"Queue size: {self.audio_queue.qsize()}/10")
                time.sleep(5)
        except KeyboardInterrupt:
            print("Stopping converter... (Press Ctrl+C again to force quit)")
        finally:
            self.stop()
    
    def stop(self):
        """Stop the converter."""
        print("Shutting down connections...")
        self.running = False
        
        if hasattr(self, 'receiver_thread'):
            self.receiver_thread.join(timeout=2.0)
        
        if hasattr(self, 'processor_thread'):
            self.processor_thread.join(timeout=2.0)
            
        if self.save_wav and hasattr(self, 'wav_file'):
            self.wav_file.close()
            print(f"WAV file saved to {self.wav_filename}")
            
        print("Converter stopped")

def main():
    parser = argparse.ArgumentParser(description="Convert ESP32 audio stream to ODAS input format")
    parser.add_argument("--esp32-ip", type=str, default="192.168.4.254", help="ESP32 IP address")
    parser.add_argument("--esp32-port", type=int, default=80, help="ESP32 HTTP port")
    parser.add_argument("--esp32-path", type=str, default="/ach1", help="ESP32 audio stream path")
    parser.add_argument("--odas-host", type=str, default="172.28.16.1", help="ODAS hostname/IP")
    parser.add_argument("--odas-port", type=int, default=1001, help="ODAS raw audio port")
    parser.add_argument("--buffer-size", type=int, default=16384, help="Audio buffer size")
    parser.add_argument("--channels", type=int, default=4, help="Number of audio channels")
    parser.add_argument("--sample-rate", type=int, default=24000, help="Audio sample rate (Hz)")
    parser.add_argument("--bits-per-sample", type=int, default=16, help="Bits per audio sample")
    parser.add_argument("--save-wav", action="store_true", help="Save audio to WAV file")
    parser.add_argument("--server-mode", action="store_true", help="Listen for ODAS to connect rather than connecting to ODAS")
    
    args = parser.parse_args()
    
    try:
        converter = ESP32AudioStreamConverter(
            esp32_ip=args.esp32_ip,
            esp32_port=args.esp32_port,
            esp32_path=args.esp32_path,
            odas_host=args.odas_host,
            odas_port=args.odas_port,
            buffer_size=args.buffer_size,
            channels=args.channels,
            sample_rate=args.sample_rate,
            bits_per_sample=args.bits_per_sample,
            save_wav=args.save_wav,
            server_mode=args.server_mode
        )
        
        converter.start()
    except KeyboardInterrupt:
        print("Process interrupted by user")
    except Exception as e:
        print(f"Error starting converter: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
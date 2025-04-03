#!/usr/bin/env python3
import socket
import struct
import wave
import argparse
import numpy as np
import time
from threading import Thread
import queue
import os

class ESP32AudioStreamConverter:
    def __init__(self, esp32_ip="192.168.4.254", esp32_port=80, 
                 odas_port=9009, buffer_size=16384, channels=4,
                 sample_rate=24000, bits_per_sample=16, save_wav=False):
        """
        Initialize the converter to transform ESP32 audio stream to ODAS input format.
        
        Args:
            esp32_ip: IP address of the ESP32 device
            esp32_port: HTTP port of the ESP32 server
            odas_port: Port where ODAS is listening for raw audio
            buffer_size: Size of audio buffer
            channels: Number of audio channels (4 for 2 stereo microphones)
            sample_rate: Audio sample rate in Hz
            bits_per_sample: Bits per audio sample
            save_wav: Whether to save received audio to WAV file
        """
        self.esp32_ip = esp32_ip
        self.esp32_port = esp32_port
        self.odas_port = odas_port
        self.buffer_size = buffer_size
        self.channels = channels
        self.sample_rate = sample_rate
        self.bits_per_sample = bits_per_sample
        self.bytes_per_sample = bits_per_sample // 8
        self.save_wav = save_wav
        self.running = False
        self.audio_queue = queue.Queue(maxsize=10)
        
        if save_wav:
            self.wav_file = wave.open(f"esp32_audio_{int(time.time())}.wav", "wb")
            self.wav_file.setnchannels(channels)
            self.wav_file.setsampwidth(self.bytes_per_sample)
            self.wav_file.setframerate(sample_rate)
    
    def _connect_to_esp32(self):
        """Establish HTTP connection to ESP32 server and request audio stream."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.esp32_ip, self.esp32_port))
        
        # Send HTTP GET request for audio stream
        request = f"GET /ach1 HTTP/1.1\r\nHost: {self.esp32_ip}\r\nConnection: keep-alive\r\n\r\n"
        s.sendall(request.encode())

        # Skip HTTP headers until we find empty line
        while True:
            line = b''
            while not line.endswith(b'\r\n'):
                c = s.recv(1)
                if not c:
                    raise ConnectionError("Connection closed before headers completed")
                line += c
            
            if line == b'\r\n':
                break
        
        print(f"Connected to ESP32 at {self.esp32_ip}:{self.esp32_port}")
        return s
    
    def _connect_to_odas(self):
        """Establish socket connection to ODAS server."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("localhost", self.odas_port))
        print(f"Connected to ODAS server on port {self.odas_port}")
        return s
        
    def _receive_audio_thread(self):
        """Thread function for receiving audio from ESP32."""
        try:
            esp32_socket = self._connect_to_esp32()
            
            while self.running:
                # Read audio data from ESP32
                # Each packet contains interleaved 16-bit samples
                # [L0, R0, L1, R1, L0, R0, L1, R1, ...]
                raw_data = esp32_socket.recv(self.buffer_size)
                if not raw_data:
                    print("Connection closed by ESP32")
                    break
                
                self.audio_queue.put(raw_data)
                
                if self.save_wav:
                    self.wav_file.writeframes(raw_data)
                    
        except Exception as e:
            print(f"Error receiving audio: {str(e)}")
        finally:
            if hasattr(self, 'esp32_socket') and self.esp32_socket:
                self.esp32_socket.close()
            self.running = False
    
    def _process_audio_thread(self):
        """Thread function for processing audio and forwarding to ODAS."""
        try:
            odas_socket = self._connect_to_odas()
            
            while self.running:
                try:
                    # Get audio data from queue
                    raw_data = self.audio_queue.get(timeout=1.0)
                    
                    # Format conversion if needed
                    # Note: ODAS typically expects signed 16-bit little-endian PCM
                    # ESP32 sends audio in the same format, so no conversion needed
                    
                    # Forward to ODAS
                    odas_socket.sendall(raw_data)
                    
                except queue.Empty:
                    continue
                    
        except Exception as e:
            print(f"Error processing audio: {str(e)}")
        finally:
            if hasattr(self, 'odas_socket') and self.odas_socket:
                self.odas_socket.close()
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
            # Keep main thread alive
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Stopping converter...")
        finally:
            self.stop()
    
    def stop(self):
        """Stop the converter."""
        self.running = False
        
        if hasattr(self, 'receiver_thread'):
            self.receiver_thread.join(timeout=2.0)
        
        if hasattr(self, 'processor_thread'):
            self.processor_thread.join(timeout=2.0)
            
        if self.save_wav and hasattr(self, 'wav_file'):
            self.wav_file.close()
            
        print("Converter stopped")

def main():
    parser = argparse.ArgumentParser(description="Convert ESP32 audio stream to ODAS input format")
    parser.add_argument("--esp32-ip", type=str, default="192.168.4.254", help="ESP32 IP address")
    parser.add_argument("--esp32-port", type=int, default=80, help="ESP32 HTTP port")
    parser.add_argument("--odas-port", type=int, default=9000, help="ODAS raw audio input port")
    parser.add_argument("--buffer-size", type=int, default=16384, help="Audio buffer size")
    parser.add_argument("--channels", type=int, default=4, help="Number of audio channels")
    parser.add_argument("--sample-rate", type=int, default=24000, help="Audio sample rate (Hz)")
    parser.add_argument("--bits-per-sample", type=int, default=16, help="Bits per audio sample")
    parser.add_argument("--save-wav", action="store_true", help="Save audio to WAV file")
    
    args = parser.parse_args()
    
    converter = ESP32AudioStreamConverter(
        esp32_ip=args.esp32_ip,
        esp32_port=args.esp32_port,
        odas_port=args.odas_port,
        buffer_size=args.buffer_size,
        channels=args.channels,
        sample_rate=args.sample_rate,
        bits_per_sample=args.bits_per_sample,
        save_wav=args.save_wav
    )
    
    converter.start()

if __name__ == "__main__":
    main()

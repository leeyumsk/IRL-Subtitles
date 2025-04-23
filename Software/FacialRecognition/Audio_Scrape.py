# whisper_using_ESP32.py
import numpy as np
import whisper
import threading
import queue
import time
import requests
import os
import sys

class AudioProcessor:
    transcription = "" #most recent transcription result
    def __init__(self):
        # Audio settings
        self.SAMPLE_RATE = 24000
        self.BUFFER_DURATION = 2  # seconds
        self.CHANNELS = 2
        self.BUFFER_SIZE = self.SAMPLE_RATE * self.BUFFER_DURATION
        
        # ESP32 settings
        self.ESP32_URL = "http://192.168.4.1/ach1"
        
        # Separate buffers for left and right channels
        self.audio_buffer_left = []
        self.audio_buffer_right = []
        self.audio_queue = queue.Queue()
        
        # Control flags
        self.running = False
        self.model = None

    def load_whisper_model(self):
        """Load Whisper model in fully offline mode"""
        print("Loading local Whisper model...")
        try:
            import whisper
            import torch
            import os
            
            model_path = os.path.join("models", "small.pt")
            if not os.path.exists(model_path):
                print(f"Model file not found at {model_path}")
                print("Please run setup_whisper.py while connected to internet first")
                return False
                
            print(f"Found model at {model_path}")
            
            # Load tiny model architecture
            self.model = whisper.load_model("small", device="cpu")
            
            # Load our saved weights
            print("Loading saved weights...")
            state_dict = torch.load(model_path, map_location="cpu")
            self.model.load_state_dict(state_dict)
            
            print("Model loaded successfully")
            return True
            
        except Exception as e:
            print(f"Error loading Whisper model: {e}")
            print("Detailed error:", repr(e))
            return False

    def start(self):
        """Start audio processing"""
        print("Starting processor...")
        
        print("Loading Whisper model...")
        # Load the Whisper model
        if not self.load_whisper_model():
            return False

        print("Starting threads...")
        self.running = True
        
        # Start receiver thread
        print("Starting receiver thread...")
        self.receiver_thread = threading.Thread(target=self.receive_audio)
        self.receiver_thread.start()
        print("Receiver thread started")
        
        # Start processing thread
        print("Starting processing thread...")
        self.process_thread = threading.Thread(target=self.process_audio)
        self.process_thread.start()
        print("Processing thread started")

        print("All threads started successfully")
        return True

    def stop(self):
        """Stop audio processing"""
        self.running = False
        if hasattr(self, 'receiver_thread'):
            self.receiver_thread.join()
        if hasattr(self, 'process_thread'):
            self.process_thread.join()

    def receive_audio(self):
        """Receive audio data from ESP32 via HTTP"""
        print(f"Starting to receive audio from {self.ESP32_URL}")
        
        while self.running:
            try:
                # Stream the audio data
                response = requests.get(self.ESP32_URL, stream=True)
                print("Connected to audio stream")
                
                for chunk in response.iter_content(chunk_size=4096):
                    if not self.running:
                        break
                        
                    if chunk:
                        # Convert bytes to numpy array of 16-bit integers
                        samples = np.frombuffer(chunk, dtype=np.int16)
                        
                        # Debug print first few samples
                        #if len(samples) > 0:
                        #    print(f"Received {len(samples)} samples. First few samples: {samples[:10]}")
                        
                        # Separate channels (even indices = left, odd indices = right)
                        left_channel = samples[::2]
                        right_channel = samples[1::2]
                        
                        self.audio_buffer_left.extend(left_channel)
                        self.audio_buffer_right.extend(right_channel)
                        
                        # If buffers are full, queue them for processing
                        if len(self.audio_buffer_left) >= self.BUFFER_SIZE:
                            audio_chunk = {
                                'left': np.array(self.audio_buffer_left[:self.BUFFER_SIZE]),
                                'right': np.array(self.audio_buffer_right[:self.BUFFER_SIZE])
                            }
                            self.audio_queue.put(audio_chunk)
                            
                            # Clear processed data from buffers
                            self.audio_buffer_left = self.audio_buffer_left[self.BUFFER_SIZE:]
                            self.audio_buffer_right = self.audio_buffer_right[self.BUFFER_SIZE:]
                            
            except requests.exceptions.RequestException as e:
                print(f"Connection error: {e}")
                print("Attempting to reconnect in 1 second...")
                time.sleep(1)
                continue

    def process_audio_chunk(self, audio_chunk):
        """Process a chunk of stereo audio with Whisper"""
        # Convert to float32 normalized between -1 and 1
        left_float32 = audio_chunk['left'].astype(np.float32) / 32768.0

        # Transcribe
        try:
            result = self.model.transcribe(left_float32, language="en")
            if result["text"].strip():  # Only print if there's actual text
                print(f"Transcription: {result['text']}")
                AudioProcessor.transcription = result['text']
                
        except Exception as e:
            print(f"Transcription error: {e}")


    def process_audio(self):
        """Process audio chunks from the queue"""
        while self.running:
            try:
                # Get audio chunk from queue with timeout
                audio_chunk = self.audio_queue.get(timeout=1.0)
                self.process_audio_chunk(audio_chunk)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Processing error: {e}")
    
    def test_esp32_connection(self):
        """Test connection to ESP32 with quick check"""
        print(f"Testing connection to {self.ESP32_URL}")
        
        try:
            # Do a quick GET request, but close it immediately
            response = requests.get(self.ESP32_URL, stream=True)
            print(f"Server is responding! Status code: {response.status_code}")
            response.close()  # Close it right away
            return True
            
        except Exception as e:
            print(f"Test failed: {type(e).__name__} - {str(e)}")
            return False

    def start_streaming(self):
        """Establish the main streaming connection"""
        print("Starting audio stream...")
        try:
            response = requests.get(self.ESP32_URL, stream=True)
            print("Connected to audio stream")
            print("Stream headers:")
            for header, value in response.headers.items():
                print(f"  {header}: {value}")
            return response
        except Exception as e:
            print(f"Failed to start stream: {e}")
            return None

    def receive_audio(self):
        """Receive audio data from ESP32 via HTTP"""
        print(f"Starting to receive audio from {self.ESP32_URL}")
        
        while self.running:
            try:
                # Establish streaming connection
                response = self.start_streaming()
                if not response:
                    print("Failed to connect, retrying in 1 second...")
                    time.sleep(1)
                    continue
                    
                for chunk in response.iter_content(chunk_size=4096):
                    if not self.running:
                        break
                        
                    if chunk:
                        # Process chunk as before...
                        samples = np.frombuffer(chunk, dtype=np.int16)
                        
                        # Debug print first few samples
                        #if len(samples) > 0:
                        #    print(f"Received {len(samples)} samples. First few samples: {samples[:10]}")
                        
                        # Separate channels (even indices = left, odd indices = right)
                        left_channel = samples[::2]
                        right_channel = samples[1::2]
                        
                        self.audio_buffer_left.extend(left_channel)
                        self.audio_buffer_right.extend(right_channel)
                        
                        # If buffers are full, queue them for processing
                        if len(self.audio_buffer_left) >= self.BUFFER_SIZE:
                            audio_chunk = {
                                'left': np.array(self.audio_buffer_left[:self.BUFFER_SIZE]),
                                'right': np.array(self.audio_buffer_right[:self.BUFFER_SIZE])
                            }
                            self.audio_queue.put(audio_chunk)
                            
                            # Clear processed data from buffers
                            self.audio_buffer_left = self.audio_buffer_left[self.BUFFER_SIZE:]
                            self.audio_buffer_right = self.audio_buffer_right[self.BUFFER_SIZE:]
                            
            except requests.exceptions.RequestException as e:
                print(f"Connection error: {e}")
                print("Attempting to reconnect in 1 second...")
                time.sleep(1)
                continue

def main():
    print("Initializing AudioProcessor()")
    processor = AudioProcessor()
    
    # Test connection first
    if not processor.test_esp32_connection():
        print("Failed to connect to ESP32. Exiting.")
        return
        
    print("AudioProcessor() initialized, starting the processor (task threads)")
    try:
        if processor.start():
            print("Audio processing started. Press Ctrl+C to stop.")
            while True:
                time.sleep(1)
        else:
            print("Failed to start audio processor")
    except KeyboardInterrupt:
        print("\nStopping audio processing...")
        processor.stop()
        print("Audio processing stopped.")
    except Exception as e:
        print(f"Unexpected error: {e}")
        processor.stop()

if __name__ == "__main__":
    main()
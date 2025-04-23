import numpy as np
import threading
import queue
import time
import requests
import os
import sys
import torch
from faster_whisper import WhisperModel

# Print device info
print("PyTorch Version:", torch.__version__)
print("CUDA Available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("CUDA Version:", torch.version.cuda)
    print("GPU Name:", torch.cuda.get_device_name(0))
else:
    print("No GPU detected")
print("Torch Compile Version:", torch.backends.cudnn.version())

# Fix Unicode printing issue (especially useful on Windows)
sys.stdout.reconfigure(encoding='utf-8')

class AudioProcessor:
    transcription = ""  # Most recent transcription result
    
    def __init__(self):
        self.SAMPLE_RATE = 16000         # 16kHz for Whisper compatibility
        self.CHUNK_DURATION = 5          # Duration in seconds of new audio to process
        self.OVERLAP_DURATION = 3        # Seconds of audio overlap between chunks
        self.NUM_CHANNELS = 4            # Now handling 4-channel audio
        self.BUFFER_SIZE = self.SAMPLE_RATE * self.CHUNK_DURATION * self.NUM_CHANNELS  # Buffer for all channels
        
        self.ESP32_URL = "http://192.168.4.2/ach1"
        
        # Audio buffers for all four channels
        self.audio_buffers = [[] for _ in range(self.NUM_CHANNELS)]
        self.audio_queue = queue.Queue()
        
        self.running = False
        self.model = None
        self.previous_audio = np.array([], dtype=np.float32)

    def load_whisper_model(self):
        """Load Faster-Whisper model in offline mode."""
        print("Loading Faster-Whisper model...")
        try:
            MODEL_SIZE = "small"  # Change to "base", "medium", or "large" if needed
            DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
            COMPUTE_TYPE = "float16" if DEVICE == "cuda" else "int8"
            print(f"Using device: {DEVICE}")
            self.model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
            print("Model loaded successfully")
            return True
        except Exception as e:
            print(f"Error loading Faster-Whisper model: {e}")
            return False

    def start(self):
        """Start streaming and processing threads."""
        print("Starting processor...")
        if not self.load_whisper_model():
            return False
        
        self.running = True
        
        self.receiver_thread = threading.Thread(target=self.receive_audio)
        self.receiver_thread.start()
        print("Receiver thread started")
        
        self.process_thread = threading.Thread(target=self.process_audio)
        self.process_thread.start()
        print("Processing thread started")
        
        return True

    def stop(self):
        """Stop streaming and processing."""
        self.running = False
        if hasattr(self, 'receiver_thread'):
            self.receiver_thread.join()
        if hasattr(self, 'process_thread'):
            self.process_thread.join()

    def start_streaming(self):
        """Establish a streaming connection to the ESP32."""
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
        """
        Continuously receive audio data from the ESP32 via HTTP.
        Handles 4-channel audio properly.
        """
        print(f"Starting to receive audio from {self.ESP32_URL}")
        while self.running:
            try:
                response = self.start_streaming()
                if not response:
                    print("Failed to connect, retrying in 1 second...")
                    time.sleep(1)
                    continue

                for chunk in response.iter_content(chunk_size=4096):
                    if not self.running:
                        break
                    if chunk:
                        # Convert bytes to a NumPy array of 16-bit integers
                        samples = np.frombuffer(chunk, dtype=np.int16)
                        
                        # Ensure samples are correctly divisible by 4
                        if len(samples) % self.NUM_CHANNELS != 0:
                            print("Warning: Audio stream data misaligned!")
                            continue

                        # Extract individual channels
                        channels = [samples[i::self.NUM_CHANNELS] for i in range(self.NUM_CHANNELS)]

                        # Store data into buffers
                        for i in range(self.NUM_CHANNELS):
                            self.audio_buffers[i].extend(channels[i])

                        # Process when buffer is full
                        if len(self.audio_buffers[0]) >= self.BUFFER_SIZE // self.NUM_CHANNELS:
                            audio_chunk = {f'channel_{i+1}': np.array(self.audio_buffers[i][:self.BUFFER_SIZE // self.NUM_CHANNELS]) for i in range(self.NUM_CHANNELS)}
                            self.audio_queue.put(audio_chunk)

                            # Trim processed samples
                            for i in range(self.NUM_CHANNELS):
                                self.audio_buffers[i] = self.audio_buffers[i][self.BUFFER_SIZE // self.NUM_CHANNELS:]
            except requests.exceptions.RequestException as e:
                print(f"Connection error: {e}")
                print("Attempting to reconnect in 1 second...")
                time.sleep(1)
                continue

    def process_audio(self):
        """
        Process queued audio chunks using Faster-Whisper.
        """
        while self.running:
            try:
                audio_chunk = self.audio_queue.get(timeout=1.0)
                self.process_audio_chunk(audio_chunk)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Processing error: {e}")

    def process_audio_chunk(self, audio_chunk):
        """
        Process a chunk of audio:
          - Choose one channel or mix them.
          - Normalize and prepare for transcription.
          - Transcribe with Faster-Whisper.
        """
        # Choose a single channel (e.g., channel 1)
        chosen_channel = audio_chunk['channel_1']

        # OR mix all channels (simple averaging)
        mixed_audio = np.mean(np.array(list(audio_chunk.values()), dtype=np.float32), axis=0)

        # Convert to float32 range (-1 to 1)
        processed_audio = mixed_audio.astype(np.float32) / 32768.0

        # Combine with previous audio for overlap
        combined_audio = np.concatenate((self.previous_audio, processed_audio))

        print("Transcribing audio chunk...")
        try:
            segments, info = self.model.transcribe(combined_audio, beam_size=5)
            transcription = " ".join(segment.text for segment in segments)
            if transcription.strip():
                print(f"Transcription: {transcription}")
                AudioProcessor.transcription = transcription
        except Exception as e:
            print(f"Transcription error: {e}")
        
        # Store last overlap duration for context in the next chunk
        overlap_samples = int(self.SAMPLE_RATE * self.OVERLAP_DURATION)
        self.previous_audio = processed_audio[-overlap_samples:] if len(processed_audio) >= overlap_samples else processed_audio

    def test_esp32_connection(self):
        """Quickly test the ESP32 connection."""
        print(f"Testing connection to {self.ESP32_URL}")
        try:
            response = requests.get(self.ESP32_URL, stream=True)
            print(f"Server is responding! Status code: {response.status_code}")
            response.close()
            return True
        except Exception as e:
            print(f"Test failed: {type(e).__name__} - {str(e)}")
            return False

def main():
    processor = AudioProcessor()
    
    if not processor.test_esp32_connection():
        print("Failed to connect to ESP32. Exiting.")
        return
        
    try:
        if processor.start():
            print("Audio processing started.")
            while True:
                time.sleep(1)
        else:
            print("Failed to start audio processor.")
    except KeyboardInterrupt:
        print("\nStopping audio processing...")
        processor.stop()
        print("Audio processing stopped.")

if __name__ == "__main__":
    main()

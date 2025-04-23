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
        # Audio and transcription settings:
        # Note: Larger chunk durations and longer overlaps naturally add more delay.
        # You can reduce CHUNK_DURATION and OVERLAP_DURATION to lower latency,
        # but be cautious as too short a duration might lose context.
        self.SAMPLE_RATE = 16000         # 16kHz for Whisper compatibility
        self.CHUNK_DURATION = 5          # Duration in seconds of new audio to process
        self.OVERLAP_DURATION = 3        # Seconds of audio overlap between chunks
        self.BUFFER_SIZE = self.SAMPLE_RATE * self.CHUNK_DURATION  # Total samples per chunk
        
        # ESP32 settings:
        self.ESP32_URL = "http://192.168.4.1/ach1"
        
        # Separate buffers for left/right channels (using left for transcription)
        self.audio_buffer_left = []
        self.audio_buffer_right = []
        self.audio_queue = queue.Queue()
        
        # Control flag and model placeholder
        self.running = False
        self.model = None
        
        # Store previous audio (for overlap)
        self.previous_audio = np.array([], dtype=np.float32)
    
    def load_whisper_model(self):
        """Load Faster-Whisper model in offline mode."""
        print("Loading Faster-Whisper model...")
        try:
            MODEL_SIZE = "small"  # Change to "base", "medium", or "large" if desired.
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
        
        # Start the audio receiver thread (handles network buffering)
        self.receiver_thread = threading.Thread(target=self.receive_audio)
        self.receiver_thread.start()
        print("Receiver thread started")
        
        # Start the processing thread (handles transcription)
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
        Note: This method buffers incoming data until a full chunk is available.
        This buffering inherently adds delay (equal to the CHUNK_DURATION).
        """
        print(f"Starting to receive audio from {self.ESP32_URL}")
        while self.running:
            try:
                response = self.start_streaming()
                if not response:
                    print("Failed to connect, retrying in 1 second...")
                    time.sleep(1)
                    continue

                # Read the streamed bytes in chunks
                for chunk in response.iter_content(chunk_size=4096):
                    if not self.running:
                        break
                    if chunk:
                        # Convert bytes to a NumPy array of 16-bit integers
                        samples = np.frombuffer(chunk, dtype=np.int16)
                        
                        # Separate channels (even indices = left, odd indices = right)
                        left_channel = samples[::2]
                        right_channel = samples[1::2]
                        
                        self.audio_buffer_left.extend(left_channel)
                        self.audio_buffer_right.extend(right_channel)
                        
                        # When enough samples are buffered, queue the chunk for processing
                        if len(self.audio_buffer_left) >= self.BUFFER_SIZE:
                            audio_chunk = {
                                'left': np.array(self.audio_buffer_left[:self.BUFFER_SIZE]),
                                'right': np.array(self.audio_buffer_right[:self.BUFFER_SIZE])
                            }
                            self.audio_queue.put(audio_chunk)
                            
                            # Remove the processed samples from the buffer
                            self.audio_buffer_left = self.audio_buffer_left[self.BUFFER_SIZE:]
                            self.audio_buffer_right = self.audio_buffer_right[self.BUFFER_SIZE:]
            except requests.exceptions.RequestException as e:
                print(f"Connection error: {e}")
                print("Attempting to reconnect in 1 second...")
                time.sleep(1)
                continue

    def process_audio(self):
        """
        Process queued audio chunks using Faster-Whisper.
        Note: The transcription process itself takes time,
        so even after buffering, processing latency adds to the overall delay.
        """
        while self.running:
            try:
                # Retrieve an audio chunk (wait up to 1 second)
                audio_chunk = self.audio_queue.get(timeout=1.0)
                self.process_audio_chunk(audio_chunk)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Processing error: {e}")

    def process_audio_chunk(self, audio_chunk):
        """
        Process a chunk of audio:
          - Convert the left channel to normalized float32.
          - Combine with previous audio to create an overlap for context.
          - Transcribe using Faster-Whisper (beam search adds to accuracy but takes extra time).
          - Update previous audio for the next chunk.
          
        The delay you observe is due to:
          1. Buffering until CHUNK_DURATION seconds of audio are received.
          2. The OVERLAP_DURATION that holds back part of the audio for context.
          3. The transcription processing time.
        """
        # Normalize left channel samples to float32 (range -1 to 1)
        new_audio = audio_chunk['left'].astype(np.float32) / 32768.0
        
        # Combine with previous audio to include overlap (ensuring context continuity)
        combined_audio = np.concatenate((self.previous_audio, new_audio))
        
        print("Transcribing audio chunk...")
        try:
            segments, info = self.model.transcribe(combined_audio, beam_size=5)
            transcription = " ".join(segment.text for segment in segments)
            if transcription.strip():
                print(f"Transcription: {transcription}")
                AudioProcessor.transcription = transcription
        except Exception as e:
            print(f"Transcription error: {e}")
        
        # Update previous_audio to the last OVERLAP_DURATION seconds of new_audio
        overlap_samples = int(self.SAMPLE_RATE * self.OVERLAP_DURATION)
        self.previous_audio = new_audio[-overlap_samples:] if len(new_audio) >= overlap_samples else new_audio

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
    
    # Test the ESP32 connection before starting
    if not processor.test_esp32_connection():
        print("Failed to connect to ESP32. Exiting.")
        return
        
    try:
        if processor.start():
            print("Audio processing started. (Note: slight delays occur due to buffering and transcription processing.)")
            while True:
                time.sleep(1)
        else:
            print("Failed to start audio processor.")
    except KeyboardInterrupt:
        print("\nStopping audio processing...")
        processor.stop()
        print("Audio processing stopped.")
    except Exception as e:
        print(f"Unexpected error: {e}")
        processor.stop()

if __name__ == "__main__":
    main()

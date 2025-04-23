import cv2
import numpy as np
import threading
import queue
import time
import requests
import sys
import torch
from faster_whisper import WhisperModel

# -------------------- Device Info & Setup --------------------
print("PyTorch Version:", torch.__version__)
print("CUDA Available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("CUDA Version:", torch.version.cuda)
    print("GPU Name:", torch.cuda.get_device_name(0))
else:
    print("No GPU detected")
print("Torch Compile Version:", torch.backends.cudnn.version())
sys.stdout.reconfigure(encoding='utf-8')

# -------------------- Endpoints --------------------
# Video from face-detection ESP32 (myssid)
VIDEO_URL = "http://192.168.4.1/stream"
# Audio from the mics ESP32 (test_ssid) - adjust port/path as needed.
AUDIO_URL = "http://192.168.4.2/ach1"  # Try modifying if necessary, e.g., "http://192.168.4.2:81/ach1"

# -------------------- Audio Processor (for ESP32 mics) --------------------
class AudioProcessor:
    transcription = ""  # Latest transcription text

    def __init__(self):
        self.SAMPLE_RATE = 16000         # 16 kHz (Whisper expects this)
        self.CHUNK_DURATION = 5          # seconds per audio chunk
        self.OVERLAP_DURATION = 3        # seconds of overlap for continuity
        self.NUM_CHANNELS = 4            # ESP32 provides 4-channel audio
        self.BUFFER_SIZE = self.SAMPLE_RATE * self.CHUNK_DURATION * self.NUM_CHANNELS

        # Use the audio endpoint for the mics ESP32.
        self.ESP32_AUDIO_URL = AUDIO_URL

        # Create one buffer per channel.
        self.audio_buffers = [[] for _ in range(self.NUM_CHANNELS)]
        self.audio_queue = queue.Queue()

        self.running = False
        self.model = None
        self.previous_audio = np.array([], dtype=np.float32)

    def load_whisper_model(self):
        print("Loading Faster-Whisper model for transcription...")
        try:
            MODEL_SIZE = "small"  # Change if needed ("base", "medium", etc.)
            DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
            COMPUTE_TYPE = "float16" if DEVICE == "cuda" else "int8"
            print(f"Using device: {DEVICE}")
            self.model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
            print("Model loaded successfully.")
            return True
        except Exception as e:
            print(f"Error loading model: {e}")
            return False

    def start(self):
        print("Starting audio processor...")
        if not self.load_whisper_model():
            return False
        self.running = True
        self.receiver_thread = threading.Thread(target=self.receive_audio, daemon=True)
        self.receiver_thread.start()
        print("Audio receiver thread started.")
        self.process_thread = threading.Thread(target=self.process_audio, daemon=True)
        self.process_thread.start()
        print("Audio processing thread started.")
        return True

    def stop(self):
        self.running = False
        if hasattr(self, 'receiver_thread'):
            self.receiver_thread.join()
        if hasattr(self, 'process_thread'):
            self.process_thread.join()

    def start_streaming(self):
        try:
            # Consider increasing timeout if needed, e.g., timeout=(10, 60)
            response = requests.get(self.ESP32_AUDIO_URL, stream=True, timeout=10)
            print("Connected to ESP32 audio stream.")
            return response
        except Exception as e:
            print(f"Failed to connect to audio stream: {e}")
            return None

    def receive_audio(self):
        print(f"Receiving audio from {self.ESP32_AUDIO_URL}...")
        while self.running:
            try:
                response = self.start_streaming()
                if not response:
                    print("Audio stream not available, retrying in 1 second...")
                    time.sleep(1)
                    continue

                for chunk in response.iter_content(chunk_size=4096):
                    if not self.running:
                        break
                    if chunk:
                        samples = np.frombuffer(chunk, dtype=np.int16)
                        if len(samples) % self.NUM_CHANNELS != 0:
                            print("Warning: Audio stream data misaligned!")
                            continue
                        channels = [samples[i::self.NUM_CHANNELS] for i in range(self.NUM_CHANNELS)]
                        for i in range(self.NUM_CHANNELS):
                            self.audio_buffers[i].extend(channels[i])
                        if len(self.audio_buffers[0]) >= self.BUFFER_SIZE // self.NUM_CHANNELS:
                            audio_chunk = {f'channel_{i+1}': np.array(self.audio_buffers[i][:self.BUFFER_SIZE // self.NUM_CHANNELS])
                                           for i in range(self.NUM_CHANNELS)}
                            self.audio_queue.put(audio_chunk)
                            for i in range(self.NUM_CHANNELS):
                                self.audio_buffers[i] = self.audio_buffers[i][self.BUFFER_SIZE // self.NUM_CHANNELS:]
            except requests.exceptions.RequestException as e:
                print(f"Audio connection error: {e}. Retrying in 1 second...")
                time.sleep(1)
                continue

    def process_audio(self):
        while self.running:
            try:
                audio_chunk = self.audio_queue.get(timeout=1.0)
                self.process_audio_chunk(audio_chunk)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Audio processing error: {e}")

    def process_audio_chunk(self, audio_chunk):
        mixed_audio = np.mean(np.array(list(audio_chunk.values()), dtype=np.float32), axis=0)
        processed_audio = mixed_audio.astype(np.float32) / 32768.0
        combined_audio = np.concatenate((self.previous_audio, processed_audio))
        print("Transcribing audio chunk...")
        try:
            segments, _ = self.model.transcribe(combined_audio, beam_size=5)
            transcription = " ".join(segment.text for segment in segments)
            if transcription.strip():
                print(f"Transcription: {transcription}")
                AudioProcessor.transcription = transcription
        except Exception as e:
            print(f"Transcription error: {e}")
        overlap_samples = int(self.SAMPLE_RATE * self.OVERLAP_DURATION)
        self.previous_audio = processed_audio[-overlap_samples:] if len(processed_audio) >= overlap_samples else processed_audio

# -------------------- Video Stream & Face Detection --------------------
net = cv2.dnn.readNetFromCaffe("deploy.prototxt", "res10_300x300_ssd_iter_140000_fp16.caffemodel")
in_width, in_height = 300, 300
mean_vals = [104, 117, 123]
conf_threshold = 0.7

def display_mjpeg_stream(url):
    print("Starting ESP32 video stream...")
    cv2.namedWindow("ESP32 Stream", cv2.WINDOW_NORMAL)
    while True:
        try:
            stream = requests.get(url, stream=True, timeout=10)
            if stream.status_code != 200:
                print(f"Failed to retrieve video stream. Status: {stream.status_code}")
                time.sleep(3)
                continue

            byte_data = b""
            for chunk in stream.iter_content(chunk_size=1024):
                byte_data += chunk
                a = byte_data.find(b'\xff\xd8')
                b = byte_data.find(b'\xff\xd9')
                if a != -1 and b != -1:
                    jpg_data = byte_data[a:b+2]
                    byte_data = byte_data[b+2:]
                    if len(jpg_data) == 0:
                        print("Warning: Empty JPEG frame received, retrying...")
                        continue
                    img_array = np.frombuffer(jpg_data, dtype=np.uint8)
                    if img_array.size == 0:
                        print("Warning: Received empty buffer, skipping frame...")
                        continue
                    frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                    if frame is None:
                        print("Warning: Decoding failed, skipping frame...")
                        continue

                    frame_height, frame_width = frame.shape[:2]
                    blob = cv2.dnn.blobFromImage(frame, 1.0, (in_width, in_height), mean_vals, swapRB=False, crop=False)
                    net.setInput(blob)
                    detections = net.forward()

                    face_found = False
                    for i in range(detections.shape[2]):
                        confidence = detections[0, 0, i, 2]
                        if confidence > conf_threshold:
                            face_found = True
                            x1 = int(detections[0, 0, i, 3] * frame_width)
                            y1 = int(detections[0, 0, i, 4] * frame_height)
                            x2 = int(detections[0, 0, i, 5] * frame_width)
                            y2 = int(detections[0, 0, i, 6] * frame_height)
                            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                            red_box_top = y2 + 5
                            red_box_bottom = y2 + 30
                            cv2.rectangle(frame, (x1, red_box_top), (x2, red_box_bottom), (0, 0, 255), -1)
                            text = AudioProcessor.transcription[-50:] if AudioProcessor.transcription else "No speech detected"
                            cv2.putText(frame, text, (x1 + 5, y2 + 25),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)
                    if not face_found:
                        red_box_height = 40
                        red_box_top = frame_height - red_box_height
                        cv2.rectangle(frame, (0, red_box_top), (frame_width, frame_height), (0, 0, 255), -1)
                        text = AudioProcessor.transcription[-50:] if AudioProcessor.transcription else "No speech detected"
                        cv2.putText(frame, text, (10, red_box_top + red_box_height - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255,255,255), 2)
                    cv2.imshow("ESP32 Stream", frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        print("Quit key pressed. Exiting video stream.")
                        return
        except requests.exceptions.RequestException as e:
            print(f"Video connection error: {e}. Retrying in 5 seconds...")
            time.sleep(5)
    cv2.destroyAllWindows()

# -------------------- Main --------------------
def main():
    print("Testing video stream connectivity...")
    try:
        test_stream = requests.get(VIDEO_URL, stream=True, timeout=10)
        if test_stream.status_code == 200:
            print("Video stream connection successful.")
            test_stream.close()
        else:
            print(f"Video stream test failed with status {test_stream.status_code}. Exiting.")
            return
    except Exception as e:
        print(f"Video stream test error: {e}. Exiting.")
        return

    audio_processor = AudioProcessor()
    if not audio_processor.start():
        print("Failed to start audio processor. Exiting.")
        return

    try:
        display_mjpeg_stream(VIDEO_URL)
    except KeyboardInterrupt:
        print("KeyboardInterrupt detected. Exiting.")
    finally:
        audio_processor.stop()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()

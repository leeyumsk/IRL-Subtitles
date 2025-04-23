import cv2
import numpy as np
import requests
import threading
import sounddevice as sd
import torch
from faster_whisper import WhisperModel
import time

# ESP32 Camera Stream URL
ESP32_URL = "http://192.168.4.1/stream"  # Update with correct IP if needed

# Global variable to store transcribed text
transcription_text = ""

# Load the face detection model
net = cv2.dnn.readNetFromCaffe("deploy.prototxt", "res10_300x300_ssd_iter_140000_fp16.caffemodel")
# Model parameters
in_width, in_height = 300, 300
mean = [104, 117, 123]
conf_threshold = 0.7

# ==================== Speech-to-Text (Runs in Background) ====================
def record_and_transcribe():
    global transcription_text
    SAMPLE_RATE = 16000  # Whisper expects 16kHz
    CHUNK_DURATION = 5  # Recording duration in seconds
    OVERLAP_DURATION = 3  # Overlap ensures no gaps

    model = WhisperModel("small", device="cuda" if torch.cuda.is_available() else "cpu", compute_type="float16")

    previous_audio = np.array([], dtype=np.float32)

    while True:
        audio = sd.rec(int((CHUNK_DURATION + OVERLAP_DURATION) * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype='float32')
        sd.wait()
        audio = audio.flatten()
        combined_audio = np.concatenate((previous_audio, audio)).astype(np.float32)

        segments, _ = model.transcribe(combined_audio, beam_size=5)
        transcription_text = " ".join(segment.text for segment in segments)
        print(f"Transcribed: {transcription_text}")

        previous_audio = audio[-int(OVERLAP_DURATION * SAMPLE_RATE):]

# Start speech-to-text in a separate thread
transcription_thread = threading.Thread(target=record_and_transcribe, daemon=True)
transcription_thread.start()

# ==================== Face Detection ====================
def display_mjpeg_stream(url):
    """ Function to handle ESP32 video stream with face detection """
    print("Connecting to ESP32 video stream...")

    while True:
        try:
            stream = requests.get(url, stream=True, timeout=5)

            if stream.status_code != 200:
                print(f"Failed to retrieve video stream. Status: {stream.status_code}")
                time.sleep(3)
                continue  # Retry after delay

            byte_data = b""
            cv2.namedWindow("ESP32 Stream", cv2.WINDOW_NORMAL)

            for chunk in stream.iter_content(chunk_size=1024):
                byte_data += chunk
                a = byte_data.find(b'\xff\xd8')  # JPEG start
                b = byte_data.find(b'\xff\xd9')  # JPEG end

                if a != -1 and b != -1:
                    jpg_data = byte_data[a:b + 2]
                    byte_data = byte_data[b + 2:]

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
                    blob = cv2.dnn.blobFromImage(frame, 1.0, (in_width, in_height), mean, swapRB=False, crop=False)
                    net.setInput(blob)
                    detections = net.forward()

                    for i in range(detections.shape[2]):
                        confidence = detections[0, 0, i, 2]
                        if confidence > conf_threshold:
                            x1 = int(detections[0, 0, i, 3] * frame_width)
                            y1 = int(detections[0, 0, i, 4] * frame_height)
                            x2 = int(detections[0, 0, i, 5] * frame_width)
                            y2 = int(detections[0, 0, i, 6] * frame_height)

                            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

                            # Draw red box directly below face
                            red_box_top = y2 + 5
                            red_box_bottom = y2 + 30
                            cv2.rectangle(frame, (x1, red_box_top), (x2, red_box_bottom), (0, 0, 255), -1)

                            # Display transcribed text inside red box
                            text = transcription_text[-50:] if transcription_text else "No speech detected"
                            cv2.putText(frame, text, (x1 + 5, y2 + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

                    cv2.imshow("ESP32 Stream", frame)

                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break

        except requests.exceptions.RequestException as e:
            print(f"Connection error: {e}. Retrying in 5 seconds...")
            time.sleep(5)

    cv2.destroyAllWindows()

# Start video stream in a separate thread
video_thread = threading.Thread(target=display_mjpeg_stream, args=(ESP32_URL,), daemon=True)
video_thread.start()

video_thread.join()

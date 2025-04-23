import cv2
import numpy as np
import requests
import threading
import sounddevice as sd
import torch
from faster_whisper import WhisperModel
import time

# -------------------- Global Variables & Model Setup --------------------
# Global transcription text that will be updated by the audio thread.
transcription_text = ""

# ESP32 Camera Stream URL (update if needed)
ESP32_URL = "http://192.168.4.1/stream"

# Load face detection model files (ensure these files are in the working directory)
net = cv2.dnn.readNetFromCaffe("deploy.prototxt", "res10_300x300_ssd_iter_140000_fp16.caffemodel")
in_width, in_height = 300, 300
mean = [104, 117, 123]
conf_threshold = 0.7

# -------------------- Audio Transcription (Mic Input) --------------------
def record_and_transcribe():
    """
    Continuously records audio from the computer's microphone,
    transcribes it using Faster-Whisper, and updates the global transcription_text.
    """
    global transcription_text
    SAMPLE_RATE = 16000         # Whisper expects 16kHz audio.
    CHUNK_DURATION = 5          # Duration (seconds) for each recording chunk.
    OVERLAP_DURATION = 3        # Seconds of overlap to maintain context between chunks.

    # Set device and compute type for the model
    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    print(f"Loading Faster-Whisper model on {device}...")
    model = WhisperModel("small", device=device, compute_type=compute_type)
    print("Audio transcription model loaded.")

    previous_audio = np.array([], dtype=np.float32)

    while True:
        # Record a new chunk (including overlap)
        total_duration = CHUNK_DURATION + OVERLAP_DURATION
        audio = sd.rec(int(total_duration * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype='float32')
        sd.wait()
        audio = audio.flatten()

        # Concatenate the last overlap from the previous chunk with the new recording
        combined_audio = np.concatenate((previous_audio, audio)).astype(np.float32)

        try:
            segments, _ = model.transcribe(combined_audio, beam_size=5)
            transcription_text = " ".join(segment.text for segment in segments)
            print(f"Transcribed: {transcription_text}")
        except Exception as e:
            print(f"Transcription error: {e}")

        # Store the last OVERLAP_DURATION seconds for continuity
        previous_audio = audio[-int(OVERLAP_DURATION * SAMPLE_RATE):]

# -------------------- Video Stream & Face Detection --------------------
def display_mjpeg_stream(url):
    """
    Connects to the ESP32 video stream, performs face detection,
    and overlays the latest transcription text onto the frame.
    """
    global transcription_text
    print("Connecting to ESP32 video stream...")
    cv2.namedWindow("ESP32 Stream", cv2.WINDOW_NORMAL)

    while True:
        try:
            stream = requests.get(url, stream=True, timeout=5)
            if stream.status_code != 200:
                print(f"Failed to retrieve video stream. Status: {stream.status_code}")
                time.sleep(3)
                continue

            byte_data = b""
            for chunk in stream.iter_content(chunk_size=1024):
                byte_data += chunk
                a = byte_data.find(b'\xff\xd8')  # JPEG start marker
                b = byte_data.find(b'\xff\xd9')  # JPEG end marker

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
                    blob = cv2.dnn.blobFromImage(frame, 1.0, (in_width, in_height), mean, swapRB=False, crop=False)
                    net.setInput(blob)
                    detections = net.forward()

                    face_found = False
                    # Process all detected faces
                    for i in range(detections.shape[2]):
                        confidence = detections[0, 0, i, 2]
                        if confidence > conf_threshold:
                            face_found = True
                            x1 = int(detections[0, 0, i, 3] * frame_width)
                            y1 = int(detections[0, 0, i, 4] * frame_height)
                            x2 = int(detections[0, 0, i, 5] * frame_width)
                            y2 = int(detections[0, 0, i, 6] * frame_height)
                            
                            # Draw a green rectangle around the face.
                            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                            
                            # Draw a red box directly below the face.
                            red_box_top = y2 + 5
                            red_box_bottom = y2 + 30
                            cv2.rectangle(frame, (x1, red_box_top), (x2, red_box_bottom), (0, 0, 255), -1)
                            
                            # Overlay transcription text inside the red box.
                            text = transcription_text[-50:] if transcription_text else "No speech detected"
                            cv2.putText(frame, text, (x1 + 5, y2 + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

                    # If no faces were detected, overlay the transcription in a red box at the bottom.
                    if not face_found:
                        red_box_height = 40
                        red_box_top = frame_height - red_box_height
                        cv2.rectangle(frame, (0, red_box_top), (frame_width, frame_height), (0, 0, 255), -1)
                        text = transcription_text[-50:] if transcription_text else "No speech detected"
                        cv2.putText(frame, text, (10, red_box_top + red_box_height - 10), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

                    cv2.imshow("ESP32 Stream", frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        print("Quit key pressed. Exiting video stream.")
                        return

        except requests.exceptions.RequestException as e:
            print(f"Connection error: {e}. Retrying in 5 seconds...")
            time.sleep(5)

    cv2.destroyAllWindows()

# -------------------- Main Function --------------------
def main():
    # Start the transcription thread (using mic input)
    transcription_thread = threading.Thread(target=record_and_transcribe, daemon=True)
    transcription_thread.start()

    # Start processing the video stream with face detection and overlay
    display_mjpeg_stream(ESP32_URL)

if __name__ == "__main__":
    main()

import os
import requests
import cv2
import numpy as np
from zipfile import ZipFile
from urllib.request import urlretrieve

# ========================-Downloading Assets-========================
def download_and_unzip(url, save_path):
    print(f"Downloading and extracting assets....", end="")
    urlretrieve(url, save_path)

    try:
        with ZipFile(save_path) as z:
            z.extractall(os.path.split(save_path)[0])
        print("Done")
    except Exception as e:
        print("\nInvalid file.", e)

URL = r"https://www.dropbox.com/s/efitgt363ada95a/opencv_bootcamp_assets_12.zip?dl=1"
asset_zip_path = os.path.join(os.getcwd(), f"opencv_bootcamp_assets_12.zip")

if not os.path.exists(asset_zip_path):
    download_and_unzip(URL, asset_zip_path)
# ====================================================================

# URL of the ESP32-S3-EYE MJPEG stream
url = 'http://192.168.4.1/stream'  # Replace with your actual MJPEG stream URL

# Function to display JPEG images from an MJPEG stream
def display_mjpeg_stream(url):
    # Open a connection to the stream
    stream = requests.get(url, stream=True)

    if stream.status_code != 200:
        print("Failed to retrieve video stream. Status code:", stream.status_code)
        return

    # Initialize an empty byte array to accumulate JPEG data
    byte_data = bytes()

    # Load the face detection model
    net = cv2.dnn.readNetFromCaffe("deploy.prototxt", "res10_300x300_ssd_iter_140000_fp16.caffemodel")
    # Model parameters
    in_width = 300
    in_height = 300
    mean = [104, 117, 123]
    conf_threshold = 0.7

    # Load the lip detection cascade
    lip_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_mcs_mouth.xml')

    # Initialize lip movement tracking variables
    prev_upper_lip_y = None
    prev_lower_lip_y = None
    lip_movement_threshold = 4
    movement_count = 0

    win_name = "Camera Preview"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)

    # Process the stream to display frames
    for chunk in stream.iter_content(chunk_size=1024):
        byte_data += chunk
        print(f"Received chunk of size: {len(chunk)} bytes")  # Debugging line

        # Look for JPEG frame boundaries in the stream
        a = byte_data.find(b'\xff\xd8')  # Start of JPEG
        b = byte_data.find(b'\xff\xd9')  # End of JPEG

        if a != -1 and b != -1:
            # Extract the JPEG image data from the byte stream
            jpg_data = byte_data[a:b + 2]
            byte_data = byte_data[b + 2:]

            # Check if the extracted JPEG data is valid (non-empty)
            if len(jpg_data) > 0:
                # Decode the JPEG image into an OpenCV-compatible format
                img_array = np.frombuffer(jpg_data, dtype=np.uint8)
                frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

                # Perform face detection
                if frame is not None:
                    frame = cv2.flip(frame, 1)
                    frame_height = frame.shape[0]
                    frame_width = frame.shape[1]

                    # Create a 4D blob from a frame
                    blob = cv2.dnn.blobFromImage(frame, 1.0, (in_width, in_height), mean, swapRB=False, crop=False)
                    net.setInput(blob)
                    detections = net.forward()

                    face_detected = False  # Variable to check if a face is detected

                    # Process face detection
                    for i in range(detections.shape[2]):
                        confidence = detections[0, 0, i, 2]
                        if confidence > conf_threshold:
                            face_detected = True  # Mark that a face is detected
                            x_left_bottom = int(detections[0, 0, i, 3] * frame_width)
                            y_left_bottom = int(detections[0, 0, i, 4] * frame_height)
                            x_right_top = int(detections[0, 0, i, 5] * frame_width)
                            y_right_top = int(detections[0, 0, i, 6] * frame_height)

                            cv2.rectangle(frame, (x_left_bottom, y_left_bottom), (x_right_top, y_right_top), (0, 255, 0))
                            label = "Confidence: %.4f" % confidence
                            label_size, base_line = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)

                            cv2.rectangle(
                                frame,
                                (x_left_bottom, y_left_bottom - label_size[1]),
                                (x_left_bottom + label_size[0], y_left_bottom + base_line),
                                (255, 255, 255),
                                cv2.FILLED,
                            )
                            cv2.putText(frame, label, (x_left_bottom, y_left_bottom), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0))

                            # Perform lip detection
                            face_region = frame[y_left_bottom:y_right_top, x_left_bottom:x_right_top]
                            if face_region.size > 0:
                                gray_face = cv2.cvtColor(face_region, cv2.COLOR_BGR2GRAY)
                                lip_region = gray_face[int(face_region.shape[0] * 0.5):, :]  # Focus on lower half of the face
                                lips = lip_cascade.detectMultiScale(lip_region, scaleFactor=1.3, minNeighbors=5, minSize=(20, 10))

                                for (lx, ly, lw, lh) in lips:
                                    if lh > 10:  # Ensure lip height is above a threshold
                                        cv2.rectangle(frame,
                                                      (x_left_bottom + lx, y_left_bottom + ly + int(face_region.shape[0] * 0.5)),
                                                      (x_left_bottom + lx + lw, y_left_bottom + ly + int(face_region.shape[0] * 0.5) + lh),
                                                      (255, 0, 0), 2)

                                        upper_lip_y = y_left_bottom + ly + int(face_region.shape[0] * 0.5)
                                        lower_lip_y = upper_lip_y + lh

                                        # Detect lip movement
                                        if prev_upper_lip_y is not None and prev_lower_lip_y is not None:
                                            lip_movement = abs(upper_lip_y - prev_upper_lip_y) + abs(lower_lip_y - prev_lower_lip_y)

                                            if lip_movement > lip_movement_threshold and lip_movement < 10:
                                                movement_count += 1
                                                print(f"Lips Moving (possible speech) - Count: {movement_count}")

                                        prev_upper_lip_y = upper_lip_y
                                        prev_lower_lip_y = lower_lip_y

                    # Display inference time
                    t, _ = net.getPerfProfile()
                    label = "Inference time: %.2f ms" % (t * 1000.0 / cv2.getTickFrequency())
                    cv2.putText(frame, label, (0, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0))

                    # Show the frame
                    cv2.imshow(win_name, frame)

                    # Press 'q' to exit the display loop
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
            else:
                print("Failed to decode frame")
        else:
            print("Incomplete JPEG frame")

    # Close the OpenCV display window
    cv2.destroyAllWindows()

# Run the function to display the MJPEG stream
display_mjpeg_stream(url)
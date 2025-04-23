import os
import cv2
import sys
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

s = 0
if len(sys.argv) > 1:
    s = sys.argv[1]

source = cv2.VideoCapture(s)
win_name = "Camera Preview"
cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)

# Diagnostic Code to Figure out the Haar Cascade Mouth .xml file
print("OpenCV data directory:", cv2.data.haarcascades)

# List all files in the haarcascades directory
try:
    haarcascade_files = os.listdir(cv2.data.haarcascades)
    print("\nAvailable cascade files:")
    for file in haarcascade_files:
        print(f"- {file}")
except Exception as e:
    print(f"Error accessing directory: {e}")

# Try to load the classifier and print detailed result
cascade_path = cv2.data.haarcascades + 'haarcascade_mcs_mouth.xml'
print(f"\nTrying to load cascade from: {cascade_path}")
print(f"File exists: {os.path.exists(cascade_path)}")

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

while cv2.waitKey(1) != 27:
    has_frame, frame = source.read()
    if not has_frame:
        break
    frame = cv2.flip(frame, 1)
    frame_height = frame.shape[0]
    frame_width = frame.shape[1]

    # Create a 4D blob from a frame
    blob = cv2.dnn.blobFromImage(frame, 1.0, (in_width, in_height), mean, swapRB=False, crop=False)
    net.setInput(blob)
    detections = net.forward()

    face_detected = False  # Variable to check if a face is detected

    # Process face detection first
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

            # Draw the rectangle below the face
            offset_x = int((x_right_top - x_left_bottom) * 0.25)
            offset_y = int((y_right_top - y_left_bottom) * 0.1)
            rect_width = int((x_right_top - x_left_bottom) * 0.5)
            rect_height = int((y_right_top - y_left_bottom) * 0.2)

            rect_top_left = (x_left_bottom + offset_x, y_right_top + offset_y)
            rect_bottom_right = (rect_top_left[0] + rect_width, rect_top_left[1] + rect_height)

            cv2.rectangle(frame, rect_top_left, rect_bottom_right, (0, 0, 255), 2)

    # If no face is detected, draw a rectangle at the bottom of the screen
    if not face_detected:
        # Rectangle parameters at the bottom of the screen
        rect_width = int(frame_width * 0.8)  # Width relative to screen width
        rect_height = int(frame_height * 0.1)  # Height relative to screen height
        rect_top_left = (int(frame_width * 0.1), frame_height - rect_height - 10)  # 10px margin from the bottom
        rect_bottom_right = (rect_top_left[0] + rect_width, frame_height - 10)

        # Draw the rectangle at the bottom
        cv2.rectangle(frame, rect_top_left, rect_bottom_right, (0, 0, 255), 2)

        # Optional: You can also add text inside the rectangle
        text = "No face detected"
        text_size, _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        text_x = rect_top_left[0] + (rect_width - text_size[0]) // 2  # Center the text
        text_y = rect_top_left[1] + (rect_height + text_size[1]) // 2  # Center vertically
        cv2.putText(frame, text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    # Display inference time
    t, _ = net.getPerfProfile()
    label = "Inference time: %.2f ms" % (t * 1000.0 / cv2.getTickFrequency())
    cv2.putText(frame, label, (0, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0))

    cv2.imshow(win_name, frame)

source.release()
cv2.destroyWindow(win_name)
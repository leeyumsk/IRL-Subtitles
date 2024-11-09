import requests
import cv2
import numpy as np

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

                # Display the frame if it's correctly decoded
                if frame is not None:
                    cv2.imshow("MJPEG Stream", frame)
                else:
                    print("Failed to decode frame")

                # Press 'q' to exit the display loop
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            else:
                print("No JPEG data extracted")
        else:
            print("Incomplete JPEG frame")

    # Close the OpenCV display window
    cv2.destroyAllWindows()

# Run the function to display the MJPEG stream
display_mjpeg_stream(url)

import os
import cv2
import numpy as np
import requests 
import sys
from zipfile import ZipFile
from urllib.request import urlretrieve

video_url = "http://192.168.4.1"
response = requests.get(video_url, stream=True)

for chunk in response.iter_content(chunk_size=1024):

       # Decode the video frame

       decoded_image = cv2.imdecode(np.frombuffer(chunk, dtype=np.uint8), cv2.IMREAD_COLOR)



       # Display the frame

       cv2.imshow('Video Stream', decoded_image)

       if cv2.waitKey(1) & 0xFF == ord('q'):  # Press 'q' to quit

           break

cv2.destroyAllWindows()

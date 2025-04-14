# Hardware
All of the hardware for the project.

## PCB

The PCB has gone through many revisions before it was eventually ordered and printed. The older version are in previous versions branch.

### Version 3.2
Version 3.2 is tha iteration that is used for this guide, where there in now only one ESP32-S3 on the sides of the frames. This has two spots to place a battery on where the battery WITH LOW BATTERY SHUTOFF to the board and on to use with a socketed BMS designed like the one from adafuit, [PowerBoost 500 Charger](https://www.adafruit.com/product/1944). The adapter for the eye has also change to pass through the audio data to the other board.

Version 3.2
<img src="/Media/ESP32S3GlassV3.2.png">
These are the pin out for the arm boards.
|Right| | |Left| | 
| ------------- | ------- | - | ------- | ------------- |
| GPIO 15 | GPIO 13 (WS) | | GND | WS | 
| GPIO 9 | GPIO 14 (SCK) | | 3V3 | SCK| 
| GPIO 10 | GPIO 21 (SD) | | x | x | 
| GPIO 11 | 3V3 | | x | SDin | 
| GPIO 12 | GND | | x | LB3v3 |

Eye Adapter Board pins:
| Top | | | | | |
| ------ | ----- | ----- | ---- | ---- | ---- |
| x | x | LB3v3 | SD | SCK | WS|
| GND | IO46 | IO45 | IO3 | IO0 | 3V3 | 
| Bottom | | | | | |
| IO43 | IO21 | IO44 | IO47 | IO48 | GND |
| X | LB3v3 | SD | SCK | WS | 3V3 | 

In the hardware folder is all the production files that is needed to order the PCBs.

## Frames
<img src="/Media/assemblypic.png">
The frames are designed to clip together without requiring a trip to the hardware store.
The CAD model is parametrically modeled to assist with personalization.
The CAD work was done in onshape and is publicly available.
https://cad.onshape.com/documents/a7485a7ae3b222abdb51885d/w/8202e3e3be7d45f8a3fb9981/e/ac120f3095f84bb498783c7c


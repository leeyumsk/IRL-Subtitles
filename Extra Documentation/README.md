# Extra Documentation

Here is where all the different files on the components, configurations, testing documents are located.

## Pin outs

(*reference to image in folder img added later once glasses are fully put together*)

Arm boards:
|Right| | |Left| | 
| ------------- | ------- | - | ------- | ------------- |
| GPIO 15 | GPIO 13 (WS) | | GND | WS | 
| GPIO 9 | GPIO 14 (SCK) | | 3V3 | SCK| 
| GPIO 10 | GPIO 21 (SD) | | x | x | 
| GPIO 11 | 3V3 | | x | SDin | 
| GPIO 12 | GND | | x | LB3v3 |

GPIO 41, 42, and 2 are used for the mics

There are more free pin on the ESP32S3 that are currently not being used, refer to the ESP32S3 documentation to see what pins are not tied to other functions. There is no reset button so boards will need to manually unplugged with the button held down for the first time.

Eye Adapter Board pins:
| Top | | | | | |
| ------ | ----- | ----- | ---- | ---- | ---- |
| x | x | LB3v3 | SD | SCK | WS|
| GND | IO46 | IO45 | IO3 | IO0 | 3V3 | 
| Bottom | | | | | |
| IO43 | IO21 | IO44 | IO47 | IO48 | GND |
| X | LB3v3 | SD | SCK | WS | 3V3 | 

## Testing
There was a variety of tests done to figure out some of the specifications of the project.

[Audio localization](/Extra%20Documentation/Audio%20localization.md)

[Testing Audio inputs](/Extra%20Documentation/Tesing%20Audio%20inputs.md)

[Face Detection](/Extra%20Documentation/Face%20Detection.md)

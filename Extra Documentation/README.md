# Extra Documentation

Here is where all the different files on the components, configurations, testing documents are located.

## Pinouts

(*reference to image in folder img added later once glasses are fully put together*)

|Left| | |Right| |
| ------------- | ------- | - | ------- | ------------- |
| GND | GPIO 12 | | GPIO 15 | GPIO 16 |
| 3V3 | GPIO 11| | GPIO 9| GPIO 43 (TX0) |
| GPIO 44 (RX0) | GPIO 10 | | GPIO 10 | GPIO 44 (RX0) |
| GPIO 43 (TX0) | GPIO 9| | GPIO 11 | 3V3 |
| GPIO 16 | GPIO 15 | | GPIO 12 | GND |

There are more free pin on the ESP32 that are currently not being used, refer to the ESP32 documentation to see what pins are not tied to other functions.

## Testing
There was a variety of tests done to figure out some of the specifications of the project.

[Audio localization](/Extra%20Documentation/Audio%20localization.md)

[Testing Audio inputs](/Extra%20Documentation/Tesing%20Audio%20inputs.md)

[Face Detection](/Extra%20Documentation/Face%20Detection.md)

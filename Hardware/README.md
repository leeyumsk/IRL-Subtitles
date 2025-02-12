# Hardware
All of the hardware for the project.

## PCB

The PCB has gone through many revisions before it was eventually ordered and printed.

### Version 1.0

Version 1.0 was the version that was started in Spring of 2024 this design was made only to capture analog audio. This version was made, but unable to test due to the inconsistent soldering because of the unmasked PCB.

<img src="/Media/memsBoardV1.png">
(*add image of PCB from last year*)

### Version 1.2

Version 1.2 was the version that was after figuring out that the ESP32 platform was going to be used. This needed to be programmed with an external uart chip though the header pins. The header pins are planned to be used for board to board communication and power transfer.

<img src="/Media/ESP32GlassV1.2.png">

### Version 1.3
Version 1.3 had the introduction of a usb-uart chip to program the board.

<img src="/Media/ESP32GlassV1.3.png">

### Version 2.0

Version 2.0 was the first version with the ESP32-S3 as the microcontroller to be used. This was an improvement as it meant that there was no need for the usb to Uart bridge that was needed to program the chip.

<img src="/Media/ESP32S3GlassV2.0.png">

### Version 2.1 & 2.2

Versions 2.1 and 2.2 are the second iterations of board with the ESP32-S3 with the correct footprint. There are the addition of mouse bites to be printed by an external manufacturer, and layout changes, moving the usb incase of signal degeneration. The changes between the between 2.1 and 2.2 are only the mouse bites that connect the two halfs.

<img src="/Media/ESP32S3GlassV2.1.png">

### Version 3.0

Versions 3.0 is an iteration with diffrent mics, the MSM261S4030H0R, on the board. This was the plan to use to be easier to solder on but at the time of ordering there where none in stock and were obsolete. There is also the addition of an addapter board for the ESP32-S3 Eye. This also adds a port to connect a battery WITH A BMS to the board.

<img src="/Media/ESP32S3GlassV3.0.png">

### Version 3.1

Version 3.1 is the second itteration of spring 2025, where there in now only one ESP32-S3 on the sides of the frames. This has two spots to place a battery on where the battery WITH A BMS to the board and on to use with a socketed BMS designed like the one from adafuit, [PowerBoost 500 Charger](https://www.adafruit.com/product/1944). The addapter for the eye has also change to pass through the audio data to the other board.

<img src="/Media/ESP32S3GlassV3.1.png">

### Version 3.2 & 3.3
Version 3.2 and 3.3 are the same as 3.1 and 3.0 respectivly, where the only chanage is the mics, same as that are on version 2.2. This had only had some small routing configuration and that had to be done.

Version 3.2
<img src="/Media/ESP32S3GlassV3.2.png">
Version 3.3
<img src="/Media/ESP32S3GlassV3.3.png">

## Frames

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

Versions 2.1 and 2.2 are the current version that is being tested. There are the addition of mouse bites to be printed by an external manufacturer, and layout changes, moving the usb incase of signal degeneration. The changes between the between 2.1 and 2.2 are only the mouse bites that connect the two halfs.

<img src="/Media/ESP32S3GlassV2.1.png">

## Frames

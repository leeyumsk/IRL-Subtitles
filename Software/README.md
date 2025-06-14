# IRL-Subtitles

Using techniques similar to human perception to localize sounds and speakers.

## Project Details

The final goal of the project is to make AR-Glasses that can display text taken from microphones to be displayed on a heads up display to the user. The system integrates a microphone array, and a camera to localize sound, transcribe speech, and visually present captions on a laptop screen connected to the glasses. This project would ideally be combined with a smart glass display/platform in the future.

<img src="/Media/OSHE_Logo_300PPI.png" width="250" >

## Current State
The current state of the project is that there is no processing that is happening locally on the board, all the data is being streamed over to a computer to be processed and displayed. There are one ESP32-S3 wroom 1U that are being used to get audio and one ESP32-S3 eye that is acting as an AP, camera, and handling the data routing. This is a battery powered data colletion unit.

## Project Structure
The project consists of:
1. [Firmware](#1-firmware)
2. [Software](#2-software)
3. [Hardware](#3-hardware)
4. [Extra Documentation](#4-extra-documentation)

Each is structured into their own folders, and sub groups.

### 1. [Firmware](/Firmware/README.md)
This is the code that is running on the ESP32. Most of the code here is for data collection and transmission. This code has two main parts, one that will go on the arm board and one that goes on the eye. This was made, built, and flashed using vscode. 

#### Requirements
- ESP32 IDF
- Target set to ESP32-S3

### 2. [Software](/Software/README.md)
This is the code that will be run on the computer to process the data that is streamed. Due to time constraints the integration of the audio localization was not included in the OpenCV and speech to text display.

### 3. [Hardware](/Hardware/README.md)
This has both the PBC and KiCad files and the glasses cad models.
The main components are:
1. Arm boards - Holds the power management and mics that collect teh audio data.
2. ESP32S3 eye - Collects the visual data and acts as an access point to route the data.
3. [PowerBoost 1000 Charger](https://www.adafruit.com/product/2465) this handle the battery.
4. Frames - Holds all components in a glasses form to be a wearable design.

#### KiCad
This has the KiCad models that were to produce the boards. That includes the schematics, the PCB files, and gerber files to order the glasses.

#### Onshape
Onshape was used to the frames that the PCBs will fit in on the glasses.

### 4. [Extra Documentation](/Extra%20Documentation/README.md)
This is all the documentation that was created in the testing and researching on creating the glasses. This also has the pin outs that were used on the glasses for reference.

## What the Project could use
1. Faster processing, moving computation on the the board.
2. Better integration between programs, face detect, sound location, and speech to text.
3. Localization of sound implemented. 
4. Battery management within code.
5. Redesign/flip the ports for the eye adapter board be able to connect to eye.

## Helpful Links
https://github.com/espressif/esp-who/tree/master

## References

[ESP-idf examples softAP](https://github.com/espressif/esp-idf/blob/master/examples/wifi/getting_started/softAP/main/softap_example_main.c)

[ESP-idf examples station](https://github.com/espressif/esp-idf/tree/master/examples/wifi/getting_started/station)

[espressif esp-who ESP32-S3-EYE](https://github.com/espressif/esp-who/blob/master/docs/en/get-started/ESP32-S3-EYE_Getting_Started_Guide.md)

[GitHub Doc](https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax#links)


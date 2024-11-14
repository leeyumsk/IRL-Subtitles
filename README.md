# IRL-Subtitles

Using techniques similar to human perception to localize sounds and speakers.

## Project Details

The final goal of thi project is to make AR-Glasses that can display text taken from microphones to be displayed on a heads up display to the user. For this, we are only using off the shelf componet so that anyone can replicate the project if they so want to.

## Current State
The current state of the project is that there is no prossesing that is happening localy on the board, all the data is being streamed over to a computer to be prossesed and displayed. There are two ESP32-S3 wroom 1U that are being used to get audio and one ESP32-S3 eye that is as a AP and handleeing the data routing. There is no battery on the glasses and will need to powered bu usb on the boards (power need to go on the right board or the eye to be able to the compination)

## Project Structure
The project consists of
1. [Firmware](#1-firmware)
2. [Software](#2-software)
3. [Hardware](#3-hardware)
4. [Extra Documentation](#4-extra-documentation)

Each are stuctured into there own folders, and sub groups.

### 1. Firmware
This is the code that is running on the on the ESP32.

#### Requirements
- ESP32 IDF
- Target set to ESP32-S3

### 2. Software
This is the code that will be ran on the computer to prosses the data that is streamed.

### 3. Hardware
This has both the PBC files and the glasses cad models.

#### KiCad
This has the KiCad models that were to produce the boards. That includes the schematics, the PCB files, and gerber files to order the glasses.

#### Onshape
Onshape was used to the frames that the PCBs will fit in on the the glasses. 

### 4. Extra Documentation
This is all the documentation that was created in the testing and researching on creating the glasses. This also has the pinouts that were used on the glasses for refrence.

## What the Project could use
1. Faster prossesing, moving computaion onthe the board
2. Better intergration between programs, face detect, sound location, and speach to text.

## Helpful Links
https://github.com/espressif/esp-who/tree/master

## Refrence (remove when published)
When writting, StuckAtPrototyoe racer was used as refrence

[Example from site](https://github.com/StuckAtPrototype/Racer/blob/master/README.md?plain=1)

[GitHub Doc](https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax#links)

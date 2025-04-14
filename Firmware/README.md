# Firmware

Here is the firmware that will do on the boards. 
For both boards ESP-idf will need to be installed to flash both boards and configured in your chosen IDE. To follow along it is recommend to use VScode.
Install ESP-IDF into VScode from the vscode extensions: Marketplace and follow this guild to configure it on your computer [guide](https://docs.espressif.com/projects/vscode-esp-idf-extension/en/latest/installation.html) and install v5.3.2.

## Arm Boards

To flash the board follow the instructions at [VScode ESP-idf configuration](https://docs.espressif.com/projects/vscode-esp-idf-extension/en/latest/startproject.html) in this [folder, ESP_Arm_Boards_Station](/Firmware/Arm%20Board/ESP32_Arm_Boards_Station). This will route the data though the access point created by the ESP32S3-eye. 

Steps:
1. Configure ESP-idf
In Command Pallette / search type >ESP-IDF: Import ESP-IDF Project

2. Select target device and flashing method
Target Device: esp32s3 usb-jtag
Comp Port: com port of esp32s3 ex. com7
Flash Method: DFU

3. Import vscode configuration files
Type ">ESP-IDF: Add VS Code Configuration Folder" into the search bar
This will over write the current folder to point to where esp-idf is .

4. Build the project
Check that the bottom of the window shows the setting in step 2 (start:DFU, plug:com/port of ESP32, Chip: esp32s3 usb-jtag)

5. Flash Board
Double check the settings at the bottom of the window they should match the setting configured in step two.
Then click the lighting bolt at the bottom of the window. 

Steps 4 and 5 can be combined into 1 step by using the fire symbol that will build, flash, and monitor the board.

### Trouble shooting
There is a python script that can be run to check the output is what is expected. [playAudiofromESP32v7.py](/Firmware/Arm%20Board/ESP32_Arm_Boards_Station/playAudioFromESP32v7.py) creates a wav file that can be analysis to check that all four channels are getting audio data. The channels on the main board (right side) are channels 3 (front) and 4 (back) and on the left are channels 1 (back) and 2 (front). Will need numpy, sounddevice, and requests installed in the python environment. 
If problems arise, use the [ESP32_Arm_Board_AP](/Firmware/Arm%20Board/ESP32_Arm_Boards_AP/) to connect to and run the python script in the folder.
If trouble occurs when flashing close all terminal windows, reopen ESP-IDF terminal and flash using the following command idf.py flash

## ESP32S3-eye


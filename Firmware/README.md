# Firmware

Here is the firmware that will do on the boards. 
For both boards ESP-idf will need to be installed to flash both boards and configured in your chossen IDE. To follow along it is recomned to use VScode.
Insall ESP-IDF into VScode from the vscode extensions: Marketplace

## Arm Boards

To flash the board follow the instrutions at [VScode ESP-idf configuration](https://docs.espressif.com/projects/vscode-esp-idf-extension/en/latest/startproject.html) in this [folder, ESP_Arm_Boards_Station](/Firmware/Arm%20Board/ESP32_Arm_Boards_Station). This will route the data though the access point created by the ESP32S3-eye. 

Steps:
1. Configure ESP-idf
In Command Pallette / search type >ESP-IDF: Import ESP-IDF Project 
2. Select target divice and flashing method
Target Device: esp32s3 usb-jtag
Comp Port: com port of esp32s3 ex. com7
Flash Method: DFU
3. Import vscode configutaion files
type ">ESP-IDF: Add VS Code Configuration Folder" into the search bar
4. Build the poject

5. Flash Board
Double check the settings at the bottom of the the window they should match the setting conigured in step two.

There is a python script that can be run to check the output is what is expected. [playAudiofromESP32v7.py](/Firmware/Arm%20Board/ESP32_Arm_Boards_Station/playAudioFromESP32v7.py) creates a wav file that can be analysis to check that all four channels are getting audio data. The channels on the main board (right side) are channels 3 and 4 and on the left are channels 1 and 2. Will need numpy, sounddevice, and requests installed in the python enviroment. 
If problems arise, use the [ESP32_Arm_Board_AP](/Firmware/Arm%20Board/ESP32_Arm_Boards_AP/) to connect to and run the python script in the folder.

## ESPS3-eye


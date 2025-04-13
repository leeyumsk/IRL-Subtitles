# Firmware

Here is the firmware that will do on the boards. 
For both boards ESP-idf will need to be installed to flash both boards and configured in your chossen IDE. To follow along it is recomned to use VScode.
Insall ESP-IDF into VScode from the vscode extensions: Marketplace

## Arm Boards

To flash the board follow the instrutions at [VScode ESP-idf configuration](https://docs.espressif.com/projects/vscode-esp-idf-extension/en/latest/startproject.html) in this [folder, ESP_Arm_Boards_Station](/Firmware/Arm%20Board/ESP32_Arm_Boards_Station).
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
Double check the settinga the bottom of the the window they should match the setting conigured in step two.

## ESPS3-eye


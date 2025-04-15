#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include "esp_log.h"
#include "driver/uart.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

// Include the binary audio data (from the binary file)
extern const uint8_t audio_data[] asm("_binary_audio_file_bin_start");
extern const uint8_t audio_data_end[] asm("_binary_audio_file_bin_end");

#define UART_PORT_NUM      UART_NUM_0
#define UART_BAUD_RATE     115200
#define BUF_SIZE           4096
#define HEADER_SIZE        4
#define FOOTER_SIZE        4

static const char *TAG = "UART_AUDIO_TRANSMISSION";

// Sync header and footer for the transmission
const uint8_t sync_header[HEADER_SIZE] = {0xAA, 0xBB, 0xCC, 0xDD};
const uint8_t sync_footer[HEADER_SIZE] = {0xDE, 0xAD, 0xBE, 0xEF};

void app_main(void)
{
    // UART configuration
    const uart_config_t uart_config = {
        .baud_rate = UART_BAUD_RATE,
        .data_bits = UART_DATA_8_BITS,
        .parity    = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
    };
    uart_param_config(UART_PORT_NUM, &uart_config);
    ESP_ERROR_CHECK(uart_set_pin(UART_PORT_NUM, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
    ESP_ERROR_CHECK(uart_driver_install(UART_PORT_NUM, BUF_SIZE, BUF_SIZE, 20, NULL, 0));

    // Calculate the audio data size
    size_t data_size = audio_data_end - audio_data;

    // Prepend the sync header and then send the audio data
    //ESP_LOGI(TAG, "Sending sync header...");
    uart_write_bytes(UART_PORT_NUM, (const char*)sync_header, HEADER_SIZE);

    //ESP_LOGI(TAG, "Sending audio data...");
    size_t bytes_sent = 0;
    while (bytes_sent < data_size) {
        int sent = uart_write_bytes(UART_PORT_NUM, (const char*)&audio_data[bytes_sent], BUF_SIZE);
        if (sent < 0) {
            //ESP_LOGE(TAG, "Failed to send audio data!");
            break;
        }
        bytes_sent += sent;
    }

    //ESP_LOGI(TAG, "Transmission complete.");
    uart_write_bytes(UART_PORT_NUM, (const char*)sync_footer, FOOTER_SIZE);

    while (1) {
        vTaskDelay(pdMS_TO_TICKS(100));  // Keep task running
    }
}

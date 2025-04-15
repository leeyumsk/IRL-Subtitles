#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include "esp_log.h"
#include "driver/i2s.h"
#include "driver/uart.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "soc/i2s_struct.h"

#define I2S_SAMPLE_RATE     24000
#define I2S_BITS_PER_SAMPLE I2S_BITS_PER_SAMPLE_32BIT
#define I2S_DMA_BUF_COUNT   8
#define I2S_DMA_BUF_LEN     64

#define RECORD_TIME_SECONDS 1  // Record duration
#define BYTES_PER_SAMPLE    2  // 16-bit (2 bytes) per sample after conversion
#define UART_PORT_NUM       UART_NUM_0
#define UART_BAUD_RATE      115200
#define BUF_SIZE            4096  // UART buffer size

#define HEADER_SIZE        4
#define FOOTER_SIZE        4

// Sync header and footer for the transmission
const uint8_t sync_header[HEADER_SIZE] = {0xAA, 0xBB, 0xCC, 0xDD};
const uint8_t sync_footer[FOOTER_SIZE] = {0xDE, 0xAD, 0xBE, 0xEF};

static const char *TAG = "I2S_AUDIO";

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
    uart_driver_install(UART_PORT_NUM, BUF_SIZE, BUF_SIZE, 0, NULL, 0);

    // I2S configuration
    i2s_config_t i2s_config = {
        .mode = I2S_MODE_MASTER | I2S_MODE_RX,
        .sample_rate = I2S_SAMPLE_RATE,
        .bits_per_sample = I2S_BITS_PER_SAMPLE,
        .channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT,
        .communication_format = I2S_COMM_FORMAT_I2S,
        .dma_buf_count = I2S_DMA_BUF_COUNT,
        .dma_buf_len = I2S_DMA_BUF_LEN,
        .use_apll = false,
        .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1
    };

    i2s_pin_config_t pin_config = {
        .bck_io_num = GPIO_NUM_33,
        .ws_io_num = GPIO_NUM_25,
        .data_out_num = I2S_PIN_NO_CHANGE,
        .data_in_num = GPIO_NUM_32
    };

    // Install and configure the I2S driver
    i2s_driver_install(I2S_NUM_0, &i2s_config, 0, NULL);
    i2s_set_pin(I2S_NUM_0, &pin_config);
    i2s_set_clk(I2S_NUM_0, I2S_SAMPLE_RATE, I2S_BITS_PER_SAMPLE, I2S_CHANNEL_STEREO);

    // Set RX FIFO mode for 32-bit dual-channel
    I2S0.conf_chan.rx_chan_mod = 2;  // Mode 2: 32-bit dual-channel

    // ESP_ERROR_CHECK(i2s_driver_install(I2S_NUM_0, &i2s_config, 0, NULL));
    // ESP_ERROR_CHECK(i2s_set_pin(I2S_NUM_0, &pin_config));
    // ESP_ERROR_CHECK(i2s_set_clk(I2S_NUM_0, I2S_SAMPLE_RATE, I2S_BITS_PER_SAMPLE, I2S_CHANNEL_STEREO));

    ESP_LOGI(TAG, "I2S RX Channel configured, starting to record audio...");

    size_t total_samples = I2S_SAMPLE_RATE * RECORD_TIME_SECONDS;  // Total number of samples for the recording time
    size_t sample_index = 0;
    uint16_t *left_audio_buffer = malloc(total_samples  * BYTES_PER_SAMPLE);  // Buffer for left samples
    uint16_t *right_audio_buffer = malloc(total_samples  * BYTES_PER_SAMPLE);  // Buffer for right samples

    if (!left_audio_buffer) {
        ESP_LOGE(TAG, "Failed to allocate memory for audio buffer");
        return;
    }

    //uint64_t raw_sample;

    uint32_t raw_sample[2]; //0 is left, 1 is right

    size_t bytes_read;

    while (sample_index < total_samples) {
        i2s_read(I2S_NUM_0, &raw_sample, sizeof(raw_sample), &bytes_read, portMAX_DELAY);

        // Extract 16-bit samples from the 64-bit raw sample
        // uint16_t left_sample = (uint16_t)((raw_sample >> 44) & 0xFFFF);
        // uint16_t right_sample = (uint16_t)((raw_sample & 0xFFFFFFF) >> 12);

        uint16_t left_sample = (uint16_t)((raw_sample[0] & 0xFFFF000) >> 12); //zeroing out the other
        uint16_t right_sample = (uint16_t)((raw_sample[1] & 0xFFFF000) >> 12);  //bits cause they're
                                                                                //getting shifted out anyways

        // Store interwoven samples in the buffer (left first, then right)
        left_audio_buffer[sample_index] = left_sample;
        right_audio_buffer[sample_index] = right_sample;

        sample_index+=1;
    }

    ESP_LOGI(TAG, "Finished recording, starting to transmit audio data...");

    // Send header
    uart_write_bytes(UART_PORT_NUM, sync_header, sizeof(sync_header));

    // Flush the transmit (TX) and receive (RX) buffers
    uart_flush(UART_PORT_NUM);  // This clears both TX and RX buffers for the specified UART port

    // Send audio data
    uart_write_bytes(UART_PORT_NUM, (const char *)left_audio_buffer, total_samples * BYTES_PER_SAMPLE);
    uart_write_bytes(UART_PORT_NUM, (const char *)right_audio_buffer, total_samples * BYTES_PER_SAMPLE);

    // Send footer
    uart_write_bytes(UART_PORT_NUM, sync_footer, sizeof(sync_footer));

    ESP_LOGI(TAG, "Audio data transmitted successfully.");

    free(left_audio_buffer);
    free(right_audio_buffer);

    while (1) {
        vTaskDelay(pdMS_TO_TICKS(50));  // Keep task running
    }
}

// SPI PERIPHERAL

#include <stdio.h>
#include <string.h>
#include "driver/spi_slave.h"
#include "driver/gpio.h"
#include "esp_log.h"

#define PIN_NUM_MISO  19
#define PIN_NUM_MOSI  23
#define PIN_NUM_CLK   18
#define PIN_NUM_CS    21  // Set to 15 or 16 depending on which peripheral (match master)

#define BUFFER_SIZE   128

static const char *TAG = "PERIPHERAL_SPI";

// Data buffers
uint8_t tx_data[BUFFER_SIZE];
uint8_t rx_data[BUFFER_SIZE];

// SPI setup function for peripherals
void setup_spi_slave() {
    // SPI bus configuration
    spi_bus_config_t buscfg = {
        .mosi_io_num = PIN_NUM_MOSI,
        .miso_io_num = PIN_NUM_MISO,
        .sclk_io_num = PIN_NUM_CLK,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1
    };

    // SPI peripheral configuration
    spi_slave_interface_config_t slvcfg = {
        .spics_io_num = PIN_NUM_CS,
        .flags = 0,
        .queue_size = 1,
        .mode = 0
    };

    // Initialize the SPI bus
    ESP_ERROR_CHECK(spi_slave_initialize(SPI2_HOST, &buscfg, &slvcfg, SPI_DMA_CH_AUTO));
}

void app_main(void) {

    // Initialize tx_data with sample data
        for (int i = 0; i < BUFFER_SIZE; i++) {
            tx_data[i] = i;
        }

    ESP_LOGI(TAG, "Setting up SPI Peripheral...");
    setup_spi_slave();

    while (1) {

        spi_slave_transaction_t trans;
        memset(&trans, 0, sizeof(trans));
        trans.length = 8 * BUFFER_SIZE;  // Transaction length in bits
        trans.tx_buffer = tx_data;
        trans.rx_buffer = NULL;

        ESP_LOGI(TAG, "Waiting for data from Master...");
        ESP_ERROR_CHECK(spi_slave_transmit(SPI2_HOST, &trans, portMAX_DELAY));
        ESP_LOGI(TAG, "Data transmitted to Master:");
        for (int i = 0; i < BUFFER_SIZE; i++) {
            printf("%02X ", tx_data[i]);
        }
        printf("\n");

        memset(rx_data, 0, BUFFER_SIZE);  // Clear the rx buffer

        vTaskDelay(pdMS_TO_TICKS(50));  // Wait for 0.5 seconds before the next iteration

        // Optionally process rx_data and prepare a new tx_data response
    }
}
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_mac.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "esp_camera.h"
#include "esp_http_server.h"
#include "lwip/err.h"
#include "lwip/sys.h"
#include "driver/spi_master.h"

/* WiFi configuration */
#define EXAMPLE_ESP_WIFI_SSID      CONFIG_ESP_WIFI_SSID
#define EXAMPLE_ESP_WIFI_PASS      CONFIG_ESP_WIFI_PASSWORD
#define EXAMPLE_ESP_WIFI_CHANNEL   CONFIG_ESP_WIFI_CHANNEL
#define EXAMPLE_MAX_STA_CONN       CONFIG_ESP_MAX_STA_CONN

static const char *TAG = "wifi softAP";

/* Camera configuration */
#define CAMERA_PIN_PWDN -1
#define CAMERA_PIN_RESET -1
#define CAMERA_PIN_XCLK 15
#define CAMERA_PIN_SIOD 4
#define CAMERA_PIN_SIOC 5
#define CAMERA_PIN_D7 16
#define CAMERA_PIN_D6 17
#define CAMERA_PIN_D5 18
#define CAMERA_PIN_D4 12
#define CAMERA_PIN_D3 10
#define CAMERA_PIN_D2 8
#define CAMERA_PIN_D1 9
#define CAMERA_PIN_D0 11
#define CAMERA_PIN_VSYNC 6
#define CAMERA_PIN_HREF 7
#define CAMERA_PIN_PCLK 13

#define SPI_SCLK_OUT 21     /* SPI shared SCLK @ GPIO 21 */
#define SPI_SDO2     43     /* Serial Data Out 1 @ GPIO0 */
#define SPI_SDI2     44      /* Serial Data In 1 @ GPIO3 */
#define SPI_SDO3     45     /* Serial Data Out 2 @ GPIO45 */
#define SPI_SDI3     46     /* Serial Data In 2 @ GPIO46 */
#define SPI_CS       -1     /* Chip select is not being used, peripheral device's CS is pulled down to 0*/

// Function definitions
static void wifi_event_handler(void* arg, esp_event_base_t event_base, int32_t event_id, void* event_data);
void wifi_init_softap(void);
void init_camera();
esp_err_t stream_handler(httpd_req_t *req);
static void start_camera_server();
void init_spi_controllers();
esp_err_t ach1_handler(httpd_req_t *req);

// Global variables
spi_device_handle_t spi_device_2;
spi_device_handle_t spi_device_3;

static httpd_uri_t stream_uri = {
    .uri = "/stream",          // URI endpoint for video stream
    .method = HTTP_GET,         // HTTP GET method
    .handler = stream_handler,  // Handler function
    .user_ctx = NULL            // Optional user context
};

static httpd_uri_t ach1_uri = {
    .uri = "/ach1",             // URI endpoint for audio channel 1 stream
    .method = HTTP_GET,         // HTTP GET method
    .handler = ach1_handler,    // Handler function
    .user_ctx = NULL            // Optional user context
};

// In app_main, add after each major step:
void app_main(void) {
    ESP_LOGI(TAG, "Starting application...");
    
    esp_err_t ret = nvs_flash_init();
    while (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
      ESP_ERROR_CHECK(nvs_flash_erase());
      ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);
    ESP_LOGI(TAG, "NVS initialized successfully");

    ESP_LOGI(TAG, "Initializing WiFi in AP mode");
    wifi_init_softap();
    
    ESP_LOGI(TAG, "Initializing camera");
    init_camera();
    
    ESP_LOGI(TAG, "Starting camera server");
    start_camera_server();

    ESP_LOGI(TAG, "Initializing SPI controllers");
    init_spi_controllers();
    
    ESP_LOGI(TAG, "Setup complete");
}

/* WiFi event handler */
static void wifi_event_handler(void* arg, esp_event_base_t event_base,
                               int32_t event_id, void* event_data) {
    if (event_id == WIFI_EVENT_AP_STACONNECTED) {
        wifi_event_ap_staconnected_t* event = (wifi_event_ap_staconnected_t*) event_data;
        ESP_LOGI(TAG, "station " MACSTR " join, AID=%d", MAC2STR(event->mac), event->aid);
    } else if (event_id == WIFI_EVENT_AP_STADISCONNECTED) {
        wifi_event_ap_stadisconnected_t* event = (wifi_event_ap_stadisconnected_t*) event_data;
        ESP_LOGI(TAG, "station " MACSTR " leave, AID=%d, reason=%d",
                 MAC2STR(event->mac), event->aid, event->reason);
    }
}

/* Initialize WiFi in SoftAP mode */
void wifi_init_softap(void) {
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_ap();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT,
                                                        ESP_EVENT_ANY_ID,
                                                        &wifi_event_handler,
                                                        NULL,
                                                        NULL));

    wifi_config_t wifi_config = {
        .ap = {
            .ssid = EXAMPLE_ESP_WIFI_SSID,
            .ssid_len = strlen(EXAMPLE_ESP_WIFI_SSID),
            .channel = EXAMPLE_ESP_WIFI_CHANNEL,
            .password = EXAMPLE_ESP_WIFI_PASS,
            .max_connection = EXAMPLE_MAX_STA_CONN,
            .authmode = WIFI_AUTH_WPA2_PSK,
            .pmf_cfg = {
                    .required = true,
            },
        },
    };
    if (strlen(EXAMPLE_ESP_WIFI_PASS) == 0) {
        wifi_config.ap.authmode = WIFI_AUTH_OPEN;
    }

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_AP));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());

    ESP_LOGI(TAG, "wifi_init_softap finished. SSID:%s password:%s channel:%d",
             EXAMPLE_ESP_WIFI_SSID, EXAMPLE_ESP_WIFI_PASS, EXAMPLE_ESP_WIFI_CHANNEL);
}

/* Initialize the Camera */
void init_camera() {
    camera_config_t config;
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;
    config.pin_d0 = CAMERA_PIN_D0;
    config.pin_d1 = CAMERA_PIN_D1;
    config.pin_d2 = CAMERA_PIN_D2;
    config.pin_d3 = CAMERA_PIN_D3;
    config.pin_d4 = CAMERA_PIN_D4;
    config.pin_d5 = CAMERA_PIN_D5;
    config.pin_d6 = CAMERA_PIN_D6;
    config.pin_d7 = CAMERA_PIN_D7;
    config.pin_xclk = CAMERA_PIN_XCLK;
    config.pin_pclk = CAMERA_PIN_PCLK;
    config.pin_vsync = CAMERA_PIN_VSYNC;
    config.pin_href = CAMERA_PIN_HREF;
    config.pin_sccb_sda = CAMERA_PIN_SIOD;
    config.pin_sccb_scl = CAMERA_PIN_SIOC;
    config.pin_pwdn = CAMERA_PIN_PWDN;
    config.pin_reset = CAMERA_PIN_RESET;
    config.xclk_freq_hz = 20000000;
    config.pixel_format = PIXFORMAT_JPEG;
    config.frame_size = FRAMESIZE_VGA;
    config.jpeg_quality = 12;
    config.fb_count = 2;

    // Camera init
    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Camera Init Failed");
    }
}

/* Stream handler for HTTP */
esp_err_t stream_handler(httpd_req_t *req) {
    camera_fb_t *fb = NULL;
    esp_err_t res = ESP_OK;
    size_t _jpg_buf_len = 0;
    uint8_t *_jpg_buf = NULL;
    char *part_buf[64];

    // Set MIME type for MJPEG stream
    res = httpd_resp_set_type(req, "multipart/x-mixed-replace;boundary=123456789000000000000987654321");
    if (res != ESP_OK) {
        return res;
    }

    while (true) {
        // Get frame
        fb = esp_camera_fb_get();
        if (!fb) {
            ESP_LOGE(TAG, "Camera capture failed");
            res = ESP_FAIL;
            break;
        }
        if (fb->format != PIXFORMAT_JPEG) {
            bool jpeg_converted = frame2jpg(fb, 80, &_jpg_buf, &_jpg_buf_len);
            esp_camera_fb_return(fb);
            fb = NULL;
            if (!jpeg_converted) {
                ESP_LOGE(TAG, "JPEG compression failed");
                res = ESP_FAIL;
                break;
            }
        } else {
            _jpg_buf_len = fb->len;
            _jpg_buf = fb->buf;
        }
        // Send multipart header
        res = httpd_resp_send_chunk(req, "\r\n--123456789000000000000987654321\r\n", 37);
        if (res != ESP_OK) {
            break;
        }
        // Send JPEG header
        res = httpd_resp_send_chunk(req, "Content-Type: image/jpeg\r\nContent-Length: ", 43);
        if (res != ESP_OK) {
            break;
        }
        // Send length
        char len_str[16];
        size_t len_len = snprintf(len_str, 16, "%u\r\n\r\n", _jpg_buf_len);
        res = httpd_resp_send_chunk(req, len_str, len_len);
        if (res != ESP_OK) {
            break;
        }
        // Send JPEG data
        res = httpd_resp_send_chunk(req, (const char *)_jpg_buf, _jpg_buf_len);
        if (res != ESP_OK) {
            break;
        }
        // Free up the buffers
        if (fb) {
            esp_camera_fb_return(fb);
            fb = NULL;
            _jpg_buf = NULL;
        } else if (_jpg_buf) {
            free(_jpg_buf);
            _jpg_buf = NULL;
        }
    }
    // Clean up
    if (fb) {
        esp_camera_fb_return(fb);
    }
    if (_jpg_buf) {
        free(_jpg_buf);
    }
    return res;
}

static void start_camera_server()
{
    ESP_LOGI(TAG, "Starting HTTP server initialization");
    
    // Define the server handle
    httpd_handle_t server = NULL;

    // Server configuration
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    ESP_LOGI(TAG, "Server config created with port: %d", config.server_port);

    // Start the server
    esp_err_t err = httpd_start(&server, &config);
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "HTTP server started successfully");
        
        // Register video streaming handler
        err = httpd_register_uri_handler(server, &stream_uri);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to register stream handler: %s", esp_err_to_name(err));
        } else {
            ESP_LOGI(TAG, "Stream handler registered at URI: %s", stream_uri.uri);
        }

        // Register audio handler
        err = httpd_register_uri_handler(server, &ach1_uri);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to register audio handler: %s", esp_err_to_name(err));
        } else {
            ESP_LOGI(TAG, "Audio handler registered at URI: %s", ach1_uri.uri);
        }
    } else {
        ESP_LOGE(TAG, "Failed to start HTTP server: %s", esp_err_to_name(err));
    }
}

/* Init SPI Controllers 2 and 3 */
void init_spi_controllers()
{
    //Init Spi 2
    spi_bus_config_t buscfg_2 = {
        .mosi_io_num = SPI_SDO2,
        .miso_io_num = SPI_SDI2,
        .sclk_io_num = SPI_SCLK_OUT,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1
    };
    spi_device_interface_config_t devcfg_2 = {
        .clock_speed_hz = SPI_MASTER_FREQ_10M,
        .mode = 0,
        .spics_io_num = SPI_CS, //chip select is not used, it will just be driven to high on peripheral device
        .queue_size = 1
    };
    ESP_ERROR_CHECK(spi_bus_initialize(SPI2_HOST, &buscfg_2, SPI_DMA_CH_AUTO));
    ESP_ERROR_CHECK(spi_bus_add_device(SPI2_HOST, &devcfg_2, &spi_device_2));

    //Init Spi 3
    // spi_bus_config_t buscfg_3 = {
    //     .mosi_io_num = SPI_SDO3,
    //     .miso_io_num = SPI_SDI3,
    //     .sclk_io_num = SPI_SCLK_OUT,
    //     .quadwp_io_num = -1,
    //     .quadhd_io_num = -1
    // };
    // spi_device_interface_config_t devcfg_3 = {
    //     .clock_speed_hz = SPI_MASTER_FREQ_10M,
    //     .mode = 0,
    //     .spics_io_num = SPI_CS, //chip select is not used, it will just be driven to high on peripheral device
    //     .queue_size = 1
    // };
    // ESP_ERROR_CHECK(spi_bus_initialize(SPI3_HOST, &buscfg_3, SPI_DMA_CH_AUTO));
    // ESP_ERROR_CHECK(spi_bus_add_device(SPI3_HOST, &devcfg_3, &spi_device_3));
    return;
}

esp_err_t ach1_handler(httpd_req_t *req) {
    ESP_LOGI(TAG, "Audio handler started");
    esp_err_t res = ESP_OK;
    uint8_t *audio_buffer = NULL;
    uint8_t *ch1_buffer = NULL;
    
    // Reduced buffer sizes
    #define SAMPLES_PER_READ 512  // Reduced from 2048
    #define BYTES_PER_SAMPLE 2
    #define NUM_CHANNELS 2
    
    size_t transaction_size = SAMPLES_PER_READ * BYTES_PER_SAMPLE * NUM_CHANNELS;
    ESP_LOGI(TAG, "Transaction size will be %d bytes (%d bits)", 
             transaction_size, transaction_size * 8);
    
    // Allocate buffers
    ESP_LOGI(TAG, "Allocating buffers");
    audio_buffer = malloc(transaction_size);
    ch1_buffer = malloc(SAMPLES_PER_READ * BYTES_PER_SAMPLE);
    
    if (!audio_buffer || !ch1_buffer) {
        ESP_LOGE(TAG, "Buffer allocation failed");
        res = ESP_ERR_NO_MEM;
        goto cleanup;
    }
    ESP_LOGI(TAG, "Buffers allocated successfully");

    // Set response type and headers
    ESP_LOGI(TAG, "Setting response headers");
    if ((res = httpd_resp_set_type(req, "audio/raw")) != ESP_OK) {
        ESP_LOGE(TAG, "Failed to set response type: %s", esp_err_to_name(res));
        goto cleanup;
    }
    
    if ((res = httpd_resp_set_hdr(req, "X-Audio-Sample-Rate", "24000")) != ESP_OK ||
        (res = httpd_resp_set_hdr(req, "X-Audio-Bits-Per-Sample", "16")) != ESP_OK ||
        (res = httpd_resp_set_hdr(req, "X-Audio-Channels", "1")) != ESP_OK) {
        ESP_LOGE(TAG, "Failed to set audio headers: %s", esp_err_to_name(res));
        goto cleanup;
    }
    ESP_LOGI(TAG, "Headers set successfully");

    // Main transaction configuration
    spi_transaction_t trans = {
        .length = transaction_size * 8,  // Convert bytes to bits
        .rx_buffer = audio_buffer,
        .tx_buffer = NULL
    };

    ESP_LOGI(TAG, "Entering main streaming loop");
    while (true) {
        if (httpd_req_to_sockfd(req) < 0) {
            ESP_LOGI(TAG, "Client disconnected");
            goto cleanup;
        }

        ESP_LOGD(TAG, "Starting SPI transaction");
        res = spi_device_polling_transmit(spi_device_2, &trans);
        if (res != ESP_OK) {
            ESP_LOGE(TAG, "SPI transaction failed: %s", esp_err_to_name(res));
            goto cleanup;
        }
        ESP_LOGD(TAG, "SPI transaction complete");

        // Extract channel 1 data
        for (int i = 0; i < SAMPLES_PER_READ; i++) {
            ch1_buffer[i * 2] = audio_buffer[i * 4];         // LSB
            ch1_buffer[i * 2 + 1] = audio_buffer[i * 4 + 1]; // MSB
        }

        ESP_LOGI(TAG, "First 7 bytes of processed data:");
        for (int j = 0; j < 7; j++) {
            ESP_LOGI(TAG, "Byte %d: 0x%02x", j, ch1_buffer[j]);
        }

        ESP_LOGD(TAG, "Sending audio chunk");
        res = httpd_resp_send_chunk(req, (char*)ch1_buffer, SAMPLES_PER_READ * BYTES_PER_SAMPLE);
        if (res != ESP_OK) {
            ESP_LOGE(TAG, "Failed to send chunk: %s", esp_err_to_name(res));
            goto cleanup;
        }

        // Small delay to prevent watchdog timeout
        vTaskDelay(1);
    }

cleanup:
    ESP_LOGI(TAG, "Entering cleanup, result: %s", esp_err_to_name(res));
    if (audio_buffer) {
        free(audio_buffer);
        audio_buffer = NULL;
    }
    if (ch1_buffer) {
        free(ch1_buffer);
        ch1_buffer = NULL;
    }
    
    if (res != ESP_OK) {
        ESP_LOGI(TAG, "Sending error response");
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Stream failed");
    }
    
    ESP_LOGI(TAG, "Handler complete");
    return res;
}

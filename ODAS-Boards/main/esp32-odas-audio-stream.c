#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_wifi.h"
#include "nvs_flash.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "lwip/err.h"
#include "lwip/sys.h"
#include "lwip/sockets.h"
#include "esp_mac.h"
#include "driver/i2s_std.h"
#include "driver/gpio.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "soc/i2s_struct.h"
#include "string.h"

// WiFi configuration
#define EXAMPLE_ESP_WIFI_SSID      "myssid"
#define EXAMPLE_ESP_WIFI_PASS      "mypassword"

// I2S configuration
#define I2S_SAMPLE_RATE           24000
#define I2S_BITS_PER_SAMPLE       I2S_BITS_PER_SAMPLE_32BIT
#define I2S_DMA_BUF_COUNT         8
#define I2S_DMA_BUF_LEN           128
#define BUFFER_SIZE               8192 * 2

// ODAS streaming configuration
#define ODAS_PORT                 1001  // Port to stream audio to ODAS
#define ODAS_SERVER_IP            "192.168.4.2" // ODAS server IP (change as needed)

static const char *TAG = "WiFi_AP_Audio_Stream";

// Audio buffers with volatile qualifier
static volatile uint16_t audio_buffer_0a[BUFFER_SIZE];
static volatile uint16_t audio_buffer_0b[BUFFER_SIZE];
size_t bufIndexA = 0;
size_t bufIndexB = 0;
static volatile bool buffer_sel = true;

// Socket for ODAS streaming
static int odas_socket = -1;
static struct sockaddr_in odas_server_addr;
static bool odas_streaming_active = false;
static TaskHandle_t odas_task_handle = NULL;

// Forward declarations
static void wifi_event_handler(void *arg, esp_event_base_t event_base, int32_t event_id, void *event_data);
static esp_err_t wifi_init_sta(void);
void setup_i2s(void);
static esp_err_t ach1_handler(httpd_req_t *req);
static void start_webserver(void);
static void odas_streaming_task(void *pvParameters);

i2s_chan_handle_t rx_handle_0;
i2s_chan_handle_t rx_handle_1;

// WiFi event handler function for a station
static void wifi_event_handler(void *arg, esp_event_base_t event_base, int32_t event_id, void *event_data) {
    if (event_base == WIFI_EVENT) {
        if (event_id == WIFI_EVENT_STA_START) {
            ESP_LOGI(TAG, "WiFi station started, attempting to connect...");
            esp_wifi_connect();
        } else if (event_id == WIFI_EVENT_STA_DISCONNECTED) {
            ESP_LOGI(TAG, "WiFi disconnected, attempting to reconnect...");
            esp_wifi_connect();
        }
    } else if (event_base == IP_EVENT) {
        if (event_id == IP_EVENT_STA_GOT_IP) {
            ip_event_got_ip_t* event = (ip_event_got_ip_t*) event_data;
            ESP_LOGI(TAG, "Got IP: " IPSTR, IP2STR(&event->ip_info.ip));
            
            // Start ODAS streaming when IP is obtained
            if (odas_task_handle == NULL) {
                ESP_LOGI(TAG, "Starting ODAS streaming task");
                xTaskCreate(odas_streaming_task, "odas_stream", 4096, NULL, 5, &odas_task_handle);
            }
        }
    }
}

// WiFi initialization function
static esp_err_t wifi_init_sta(void) {
    esp_err_t ret;
    
    ESP_LOGI(TAG, "Starting WiFi initialization in station mode...");
    
    ret = esp_netif_init();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "TCP/IP adapter initialization failed");
        return ret;
    }
    
    ret = esp_event_loop_create_default();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Event loop creation failed");
        return ret;
    }
    
    esp_netif_t *sta_netif = esp_netif_create_default_wifi_sta();
    if (sta_netif == NULL) {
        ESP_LOGE(TAG, "Failed to create WiFi STA netif");
        return ESP_FAIL;
    }
    
    // Configure static IP
    esp_netif_dhcpc_stop(sta_netif); // Stop DHCP client
    
    // Set static IP address
    esp_netif_ip_info_t ip_info;
    memset(&ip_info, 0, sizeof(esp_netif_ip_info_t));
    
    // Convert IP address, gateway, and netmask strings to IP4 address format
    ESP_ERROR_CHECK(esp_netif_str_to_ip4("192.168.4.254", &ip_info.ip)); //The static IP should be 192.168.4.254
    ESP_ERROR_CHECK(esp_netif_str_to_ip4("192.168.4.1", &ip_info.gw));
    ESP_ERROR_CHECK(esp_netif_str_to_ip4("255.255.255.0", &ip_info.netmask));
    
    // Set the IP info for the station interface
    ESP_ERROR_CHECK(esp_netif_set_ip_info(sta_netif, &ip_info));
    
    ESP_LOGI(TAG, "Configured static IP: 192.168.4.254");
    
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ret = esp_wifi_init(&cfg);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "WiFi initialization failed");
        return ret;
    }
    
    // Register handlers for both WiFi and IP events
    ret = esp_event_handler_instance_register(WIFI_EVENT, 
                                            ESP_EVENT_ANY_ID, 
                                            &wifi_event_handler, 
                                            NULL, 
                                            NULL);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "WiFi event handler registration failed");
        return ret;
    }
    
    ret = esp_event_handler_instance_register(IP_EVENT,
                                            IP_EVENT_STA_GOT_IP,
                                            &wifi_event_handler,
                                            NULL,
                                            NULL);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "IP event handler registration failed");
        return ret;
    }
    
    // Configure with station mode parameters
    wifi_config_t wifi_config = {
        .sta = {
            .ssid = EXAMPLE_ESP_WIFI_SSID,
            .password = EXAMPLE_ESP_WIFI_PASS,
            .threshold.authmode = WIFI_AUTH_WPA2_PSK,
            .pmf_cfg = {
                .capable = true,
                .required = true
            },
        },
    };
    
    ret = esp_wifi_set_mode(WIFI_MODE_STA);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to set WiFi mode");
        return ret;
    }
    
    ret = esp_wifi_set_config(WIFI_IF_STA, &wifi_config);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to set WiFi config");
        return ret;
    }
    
    ret = esp_wifi_start();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start WiFi");
        return ret;
    }
    
    ESP_LOGI(TAG, "WiFi initialized in station mode with static IP");
    return ESP_OK;
}

// I2S setup function
void setup_i2s(void) {
    ESP_LOGI("I2S", "Initializing I2S peripherals...");
    // === Configure First I2S Peripheral (I2S_NUM_0) ===
    // Define the I2S channel configuration for RX
    i2s_chan_config_t chan_cfg0 = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);

    // Allocate the RX channel
    if (i2s_new_channel(&chan_cfg0, NULL, &rx_handle_0) != ESP_OK) {
        ESP_LOGE("I2S", "Failed to create I2S_0 RX channel");
        return;
    }

    // Configure the standard I2S settings
    i2s_std_config_t std_cfg0 = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(I2S_SAMPLE_RATE),
        .slot_cfg = I2S_STD_MSB_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_STEREO),
        .gpio_cfg = {
            .mclk = I2S_GPIO_UNUSED,
            .bclk = GPIO_NUM_14,
            .ws = GPIO_NUM_13,
            .dout = I2S_GPIO_UNUSED,
            .din = GPIO_NUM_21,
            .invert_flags = {
                .mclk_inv = false,
                .bclk_inv = false,
                .ws_inv = false,
            },
        },
    };

    // Initialize the RX channel in standard mode
    if (i2s_channel_init_std_mode(rx_handle_0, &std_cfg0) != ESP_OK) {
        ESP_LOGE("I2S", "Failed to initialize I2S_0 RX channel in standard mode");
        return;
    }

    // Enable the RX channel to start receiving data
    if (i2s_channel_enable(rx_handle_0) != ESP_OK) {
        ESP_LOGE("I2S", "Failed to enable I2S_0 RX channel");
    }

    // === Configure Second I2S Peripheral (I2S_NUM_1) ===
    // Define the I2S channel configuration for RX
    i2s_chan_config_t chan_cfg1 = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_1, I2S_ROLE_MASTER);

    // Allocate the RX channel
    if (i2s_new_channel(&chan_cfg1, NULL, &rx_handle_1) != ESP_OK) {
        ESP_LOGE("I2S", "Failed to create I2S_1 RX channel");
        return;
    }

    // Configure the standard I2S settings
    i2s_std_config_t std_cfg1 = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(I2S_SAMPLE_RATE),
        .slot_cfg = I2S_STD_MSB_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_STEREO),
        .gpio_cfg = {
            .mclk = I2S_GPIO_UNUSED,
            .bclk = GPIO_NUM_41,
            .ws = GPIO_NUM_42,
            .dout = I2S_GPIO_UNUSED,
            .din = GPIO_NUM_2,
            .invert_flags = {
                .mclk_inv = false,
                .bclk_inv = false,
                .ws_inv = false,
            },
        },
    };

    // Initialize the RX channel in standard mode
    if (i2s_channel_init_std_mode(rx_handle_1, &std_cfg1) != ESP_OK) {
        ESP_LOGE("I2S", "Failed to initialize I2S_1 RX channel in standard mode");
        return;
    }

    // Enable the RX channel to start receiving data
    if (i2s_channel_enable(rx_handle_1) != ESP_OK) {
        ESP_LOGE("I2S", "Failed to enable I2S_1 RX channel");
    }
    ESP_LOGI("I2S", "I2S peripherals initialized!");
}

// Start webserver function
static void start_webserver(void) {
    ESP_LOGI(TAG, "Starting webserver initialization...");
    
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.stack_size = 8192 * 2;
    config.task_priority = tskIDLE_PRIORITY + 5;
    
    httpd_handle_t server = NULL;
    
    ESP_LOGI(TAG, "Starting HTTP server on port: %d", config.server_port);
    
    esp_err_t ret = httpd_start(&server, &config);
    if (ret == ESP_OK) {
        // URI handler structure for GET /audio_stream
        httpd_uri_t audio_stream = {
            .uri       = "/ach1",
            .method    = HTTP_GET,
            .handler   = ach1_handler,
            .user_ctx  = NULL
        };
        
        // Register URI handlers
        ret = httpd_register_uri_handler(server, &audio_stream);
        if (ret == ESP_OK) {
            ESP_LOGI(TAG, "URI handler registered successfully");
        } else {
            ESP_LOGE(TAG, "Failed to register URI handler: %s", esp_err_to_name(ret));
        }
    } else {
        ESP_LOGE(TAG, "Failed to start server: %s", esp_err_to_name(ret));
    }
}

// ODAS streaming task - continuously samples and sends audio to ODAS server
static void odas_streaming_task(void *pvParameters) {
    ESP_LOGI(TAG, "ODAS streaming task started");
    
    // Create socket
    int sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (sock < 0) {
        ESP_LOGE(TAG, "Failed to create socket: errno %d", errno);
        vTaskDelete(NULL);
        return;
    }
    
    // Configure server address
    struct sockaddr_in server_addr;
    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons(ODAS_PORT);
    inet_aton(ODAS_SERVER_IP, &server_addr.sin_addr);
    
    // Connect to ODAS server
    ESP_LOGI(TAG, "Connecting to ODAS server at %s:%d", ODAS_SERVER_IP, ODAS_PORT);
    if (connect(sock, (struct sockaddr *)&server_addr, sizeof(server_addr)) < 0) {
        ESP_LOGE(TAG, "Socket connection failed: errno %d", errno);
        close(sock);
        vTaskDelete(NULL);
        return;
    }
    
    ESP_LOGI(TAG, "Connected to ODAS server");
    odas_socket = sock;
    odas_streaming_active = true;
    
    // Send audio format information (optional - ODAS might expect a specific format)
    // Format header: 4 channels, 16-bit samples, 24kHz
    uint8_t format_header[8] = {
        0x01,                       // Format version
        0x04,                       // Number of channels
        0x10, 0x00,                 // Bits per sample (16-bit, little endian)
        0xC0, 0x5D, 0x00, 0x00      // Sample rate (24000 Hz, little endian)
    };
    
    if (send(sock, format_header, sizeof(format_header), 0) < 0) {
        ESP_LOGE(TAG, "Failed to send format header: errno %d", errno);
        goto cleanup;
    }
    
    // Buffer for audio data
    uint16_t odas_buffer[BUFFER_SIZE];
    size_t bytes_read = 0;
    uint32_t raw_sample[4];  // Buffer for raw samples
    
    // Streaming loop
    while (odas_streaming_active) {
        // Read from both I2S channels and fill buffer
        for (size_t i = 0; i < BUFFER_SIZE; i += 4) {
            if ((i2s_channel_read(rx_handle_0, raw_sample, sizeof(uint32_t) * 2, &bytes_read, portMAX_DELAY)) == ESP_OK &&
                (i2s_channel_read(rx_handle_1, &raw_sample[2], sizeof(uint32_t) * 2, &bytes_read, portMAX_DELAY)) == ESP_OK) {
                
                // Convert 32-bit samples to 16-bit
                odas_buffer[i] = (uint16_t)((raw_sample[0] & 0xFFFF000) >> 12);
                odas_buffer[i+1] = (uint16_t)((raw_sample[1] & 0xFFFF000) >> 12);
                odas_buffer[i+2] = (uint16_t)((raw_sample[2] & 0xFFFF000) >> 12);
                odas_buffer[i+3] = (uint16_t)((raw_sample[3] & 0xFFFF000) >> 12);
            }
        }
        
        // Send the audio data to ODAS
        int sent = send(sock, odas_buffer, BUFFER_SIZE * sizeof(uint16_t), 0);
        if (sent < 0) {
            ESP_LOGE(TAG, "Error sending data: errno %d", errno);
            // If connection lost, attempt to reconnect
            break;
        }
        
        // Small delay to prevent watchdog issues
        vTaskDelay(1);
    }
    
cleanup:
    // Close socket and end task
    if (sock != -1) {
        close(sock);
        odas_socket = -1;
    }
    odas_streaming_active = false;
    ESP_LOGI(TAG, "ODAS streaming task ended, will attempt reconnection when network is available");
    
    // Delay before trying to reconnect
    vTaskDelay(pdMS_TO_TICKS(5000));
    
    // Start a new task to attempt reconnection
    xTaskCreate(odas_streaming_task, "odas_stream", 4096, NULL, 5, &odas_task_handle);
    
    vTaskDelete(NULL);
}

// HTTP handler for web streaming (unchanged)
static esp_err_t ach1_handler(httpd_req_t *req) {
    ESP_LOGI(TAG, "Audio handler started");
    esp_err_t res = ESP_OK;
    
    // Set response type and headers
    if ((res = httpd_resp_set_type(req, "audio/raw")) != ESP_OK) {
        ESP_LOGE(TAG, "Failed to set response type: %s", esp_err_to_name(res));
        goto cleanup;
    }
    
    if ((res = httpd_resp_set_hdr(req, "X-Audio-Sample-Rate", "24000")) != ESP_OK ||
        (res = httpd_resp_set_hdr(req, "X-Audio-Bits-Per-Sample", "16")) != ESP_OK ||
        (res = httpd_resp_set_hdr(req, "X-Audio-Channels", "4")) != ESP_OK) {
        ESP_LOGE(TAG, "Failed to set audio headers: %s", esp_err_to_name(res));
        goto cleanup;
    }

    size_t bytes_read = 0;
    uint32_t raw_sample[4];  // Buffer to hold raw left0, right0, left1, and right1 samples
    
    while (true) {
        if (httpd_req_to_sockfd(req) < 0) {
            ESP_LOGI(TAG, "Client disconnected");
            goto cleanup;
        }
        // Read from I2S
        if (buffer_sel) {
            for (bufIndexA = 0; bufIndexA < BUFFER_SIZE; bufIndexA += 4) {
                if ((i2s_channel_read(rx_handle_0, raw_sample, sizeof(uint32_t) * 2, &bytes_read, portMAX_DELAY)) == ESP_OK &&\
                    (i2s_channel_read(rx_handle_1, &raw_sample[2], sizeof(uint32_t) * 2, &bytes_read, portMAX_DELAY)) == ESP_OK) {
                    audio_buffer_0a[bufIndexA] = (uint16_t)((raw_sample[0] & 0xFFFF000) >> 12);
                    audio_buffer_0a[bufIndexA+1] = (uint16_t)((raw_sample[1] & 0xFFFF000) >> 12);
                    audio_buffer_0a[bufIndexA+2] = (uint16_t)((raw_sample[2] & 0xFFFF000) >> 12);
                    audio_buffer_0a[bufIndexA+3] = (uint16_t)((raw_sample[3] & 0xFFFF000) >> 12);
                }
            }
            //Transmitting buffer A
            res = httpd_resp_send_chunk(req, (const char *)audio_buffer_0a, BUFFER_SIZE * sizeof(uint16_t));
            bufIndexA = 0;

            buffer_sel = false;

        }else{
            ESP_LOGI(TAG, "Filling buffer B");
            for (bufIndexB = 0; bufIndexB < BUFFER_SIZE; bufIndexB += 4) {
                if ((i2s_channel_read(rx_handle_0, raw_sample, sizeof(uint32_t) * 2, &bytes_read, portMAX_DELAY)) == ESP_OK &&\
                (i2s_channel_read(rx_handle_1, &raw_sample[2], sizeof(uint32_t) * 2, &bytes_read, portMAX_DELAY)) == ESP_OK) {
                    audio_buffer_0b[bufIndexB] = (uint16_t)((raw_sample[0] & 0xFFFF000) >> 12);
                    audio_buffer_0b[bufIndexB+1] = (uint16_t)((raw_sample[1] & 0xFFFF000) >> 12);
                    audio_buffer_0b[bufIndexB+2] = (uint16_t)((raw_sample[2] & 0xFFFF000) >> 12);
                    audio_buffer_0b[bufIndexB+3] = (uint16_t)((raw_sample[3] & 0xFFFF000) >> 12);
                }
            }
            //Transmitting buffer B
            res = httpd_resp_send_chunk(req, (const char *)audio_buffer_0b, BUFFER_SIZE * sizeof(uint16_t));
            bufIndexB = 0;

            buffer_sel = true;
        }
        
        if (res != ESP_OK) {
            ESP_LOGE(TAG, "Failed to send chunk: %s", esp_err_to_name(res));
            goto cleanup;
        }
    }

cleanup:
    return res;
}

void app_main(void) {
    ESP_LOGI(TAG, "Starting application...");
    
    // Initialize NVS
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);
    ESP_LOGI(TAG, "NVS initialized");
        
    ESP_LOGI(TAG, "Initializing WiFi in Station Mode");
    
    // Initialize WiFi
    ret = wifi_init_sta();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "WiFi initialization failed");
        vTaskDelete(NULL);
        return;
    }
    ESP_LOGI(TAG, "WiFi Initialization Successful");
    
    ESP_LOGI(TAG, "Starting webserver");
    // Start webserver
    start_webserver();
    ESP_LOGI(TAG, "Webserver initialization Successful");
    
    // Initialize I2S
    setup_i2s();
    
    ESP_LOGI(TAG, "Application initialization completed");
}

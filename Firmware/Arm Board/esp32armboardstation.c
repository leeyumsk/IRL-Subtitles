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
#include "esp_mac.h"
#include "driver/i2s_std.h"
#include "driver/gpio.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "soc/i2s_struct.h"
#include "string.h"

// WiFi configuration
// #define EXAMPLE_ESP_WIFI_SSID      "test_ssid"
// #define EXAMPLE_ESP_WIFI_PASS      "test_pass"
#define EXAMPLE_ESP_WIFI_SSID      "myssid"
#define EXAMPLE_ESP_WIFI_PASS      "mypassword"
// #define EXAMPLE_MAX_STA_CONN       4

// I2S configuration
#define I2S_SAMPLE_RATE           24000
#define I2S_BITS_PER_SAMPLE       I2S_BITS_PER_SAMPLE_32BIT
#define I2S_DMA_BUF_COUNT         8
#define I2S_DMA_BUF_LEN           128
#define BUFFER_SIZE               8192 * 2

static const char *TAG = "WiFi_AP_Audio_Stream";

// Audio buffers with volatile qualifier
static volatile uint16_t audio_buffer_0a[BUFFER_SIZE];
static volatile uint16_t audio_buffer_0b[BUFFER_SIZE];
size_t bufIndexA = 0;
size_t bufIndexB = 0;
static volatile bool buffer_sel = true;

// Synchronization primitives
//static SemaphoreHandle_t buffer_mutex = NULL;
static volatile bool stream_active = false;

// Forward declarations
static void wifi_event_handler(void *arg, esp_event_base_t event_base, int32_t event_id, void *event_data);
//static esp_err_t wifi_init_softap(void);
static esp_err_t wifi_init_sta(void);
void setup_i2s(void);
static esp_err_t ach1_handler(httpd_req_t *req);
static void start_webserver(void);
//static void i2s_sampling_task(void *arg);
//static void wifi_task(void *arg);

i2s_chan_handle_t rx_handle_0;
i2s_chan_handle_t rx_handle_1;

// WiFi event handler function for an access point
// static void wifi_event_handler(void *arg, esp_event_base_t event_base, int32_t event_id, void *event_data) {
//     if (event_id == WIFI_EVENT_AP_STACONNECTED) {
//         wifi_event_ap_staconnected_t *event = (wifi_event_ap_staconnected_t *)event_data;
//         ESP_LOGI(TAG, "Station "MACSTR" joined, AID=%d", MAC2STR(event->mac), event->aid);
//     } else if (event_id == WIFI_EVENT_AP_STADISCONNECTED) {
//         wifi_event_ap_stadisconnected_t *event = (wifi_event_ap_stadisconnected_t *)event_data;
//         ESP_LOGI(TAG, "Station "MACSTR" left, AID=%d", MAC2STR(event->mac), event->aid);
//     }
// }

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
        }
    }
}


// WiFi initialization function (for AP)
// static esp_err_t wifi_init_softap(void) {
//     esp_err_t ret;
    
//     ESP_LOGI(TAG, "Starting WiFi initialization...");
    
//     ret = esp_netif_init();
//     if (ret != ESP_OK) {
//         ESP_LOGE(TAG, "TCP/IP adapter initialization failed");
//         return ret;
//     }
//     ESP_LOGI(TAG, "TCP/IP adapter initialized");
    
//     ret = esp_event_loop_create_default();
//     if (ret != ESP_OK) {
//         ESP_LOGE(TAG, "Event loop creation failed");
//         return ret;
//     }
//     ESP_LOGI(TAG, "Event loop created");
    
//     esp_netif_t *ap_netif = esp_netif_create_default_wifi_ap();
//     if (ap_netif == NULL) {
//         ESP_LOGE(TAG, "Failed to create WiFi AP netif");
//         return ESP_FAIL;
//     }
//     ESP_LOGI(TAG, "WiFi AP netif created");
    
//     wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
//     ret = esp_wifi_init(&cfg);
//     if (ret != ESP_OK) {
//         ESP_LOGE(TAG, "WiFi initialization failed");
//         return ret;
//     }
//     ESP_LOGI(TAG, "WiFi initialized");
    
//     ret = esp_event_handler_instance_register(WIFI_EVENT, 
//                                             ESP_EVENT_ANY_ID, 
//                                             &wifi_event_handler, 
//                                             NULL, 
//                                             NULL);
//     if (ret != ESP_OK) {
//         ESP_LOGE(TAG, "Event handler registration failed");
//         return ret;
//     }
//     ESP_LOGI(TAG, "Event handler registered");
    
//     wifi_config_t wifi_config = {
//         .ap = {
//             .ssid = EXAMPLE_ESP_WIFI_SSID,
//             .ssid_len = strlen(EXAMPLE_ESP_WIFI_SSID),
//             .password = EXAMPLE_ESP_WIFI_PASS,
//             .max_connection = EXAMPLE_MAX_STA_CONN,
//             .authmode = strlen(EXAMPLE_ESP_WIFI_PASS) ? WIFI_AUTH_WPA_WPA2_PSK : WIFI_AUTH_OPEN
//         },
//     };
    
//     ret = esp_wifi_set_mode(WIFI_MODE_AP);
//     if (ret != ESP_OK) {
//         ESP_LOGE(TAG, "Failed to set WiFi mode");
//         return ret;
//     }
//     ESP_LOGI(TAG, "WiFi mode set to AP");
    
//     ret = esp_wifi_set_config(WIFI_IF_AP, &wifi_config);
//     if (ret != ESP_OK) {
//         ESP_LOGE(TAG, "Failed to set WiFi config");
//         return ret;
//     }
//     ESP_LOGI(TAG, "WiFi config set");
    
//     ret = esp_wifi_start();
//     if (ret != ESP_OK) {
//         ESP_LOGE(TAG, "Failed to start WiFi");
//         return ret;
//     }
//     ESP_LOGI(TAG, "WiFi started successfully");
    
//     return ESP_OK;
// }

// Replace wifi_init_softap with wifi_init_sta
// DYNAMIC IP station
// static esp_err_t wifi_init_sta(void) {
//     esp_err_t ret;
    
//     ESP_LOGI(TAG, "Starting WiFi initialization in station mode...");
    
//     ret = esp_netif_init();
//     if (ret != ESP_OK) {
//         ESP_LOGE(TAG, "TCP/IP adapter initialization failed");
//         return ret;
//     }
    
//     ret = esp_event_loop_create_default();
//     if (ret != ESP_OK) {
//         ESP_LOGE(TAG, "Event loop creation failed");
//         return ret;
//     }
    
//     esp_netif_t *sta_netif = esp_netif_create_default_wifi_sta();
//     if (sta_netif == NULL) {
//         ESP_LOGE(TAG, "Failed to create WiFi STA netif");
//         return ESP_FAIL;
//     }
    
//     wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
//     ret = esp_wifi_init(&cfg);
//     if (ret != ESP_OK) {
//         ESP_LOGE(TAG, "WiFi initialization failed");
//         return ret;
//     }
    
//     // Register handlers for both WiFi and IP events
//     ret = esp_event_handler_instance_register(WIFI_EVENT, 
//                                             ESP_EVENT_ANY_ID, 
//                                             &wifi_event_handler, 
//                                             NULL, 
//                                             NULL);
//     if (ret != ESP_OK) {
//         ESP_LOGE(TAG, "WiFi event handler registration failed");
//         return ret;
//     }
    
//     ret = esp_event_handler_instance_register(IP_EVENT,
//                                             IP_EVENT_STA_GOT_IP,
//                                             &wifi_event_handler,
//                                             NULL,
//                                             NULL);
//     if (ret != ESP_OK) {
//         ESP_LOGE(TAG, "IP event handler registration failed");
//         return ret;
//     }
    
//     // Configure with station mode parameters
//     wifi_config_t wifi_config = {
//         .sta = {
//             .ssid = EXAMPLE_ESP_WIFI_SSID,
//             .password = EXAMPLE_ESP_WIFI_PASS,
//             .threshold.authmode = WIFI_AUTH_WPA2_PSK,
//             .pmf_cfg = {
//                 .capable = true,
//                 .required = true
//             },
//         },
//     };
    
//     ret = esp_wifi_set_mode(WIFI_MODE_STA);
//     if (ret != ESP_OK) {
//         ESP_LOGE(TAG, "Failed to set WiFi mode");
//         return ret;
//     }
    
//     ret = esp_wifi_set_config(WIFI_IF_STA, &wifi_config);
//     if (ret != ESP_OK) {
//         ESP_LOGE(TAG, "Failed to set WiFi config");
//         return ret;
//     }
    
//     ret = esp_wifi_start();
//     if (ret != ESP_OK) {
//         ESP_LOGE(TAG, "Failed to start WiFi");
//         return ret;
//     }
    
//     ESP_LOGI(TAG, "WiFi initialized in station mode");
//     return ESP_OK;
// }

// Replace wifi_init_softap with wifi_init_sta
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
    
    ESP_LOGI(TAG, "Configured static IP: 192.168.4.2");
    
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
#include "driver/i2s_std.h"
#include "driver/gpio.h"

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

        // === Configure First I2S Peripheral (I2S_NUM_1) ===
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
        
    ESP_LOGI(TAG, "Initializing WiFi in SoftAP Mode");
    
    // Initialize WiFi
    ret = wifi_init_sta();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "WiFi initialization failed");
        vTaskDelete(NULL);
        return;
    }
    ESP_LOGI(TAG, "WiFi Initilization Successful");

    // Give some time for WiFi to initialize
    //vTaskDelay(pdMS_TO_TICKS(1000));
    
    ESP_LOGI(TAG, "Starting webserver");
    // Start webserver
    start_webserver();
    ESP_LOGI(TAG, "Webserver initialization Successfully");
    
    ESP_LOGI(TAG, "WiFi task completed initialization");

    // Initialize I2S
    setup_i2s();
    
    ESP_LOGI(TAG, "Application initialization completed");
}

//Update the two lines below after 2 channels work
//Current code right now should work but is only using 1 microphone, need to add the second one and the buffer handling
//Maybe add a mutex or semaphore before buffer switching? But last time that caused issues with the I2S reading (cause of delays)

//for multiple channels and "audio/raw", the data is expected to be interleaved
// ex: [sample0, sample1] for two channels or [sample0, sample1, sample2, sample3] for four channels
// audio is packed the same way in .wav format, so it should be easy to take this and make a .wav file with two or four channels 
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
            //ESP_LOGI(TAG, "Filling buffer A");
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

        // Small delay to prevent watchdog issues
        //vTaskDelay(1);
    }

cleanup:
    return res;
}

// #include "esp_http_server.h"
// #include "esp_log.h"
// #include "esp_wifi.h"
// #include "nvs_flash.h"
// #include "esp_event.h"
// #include "esp_netif.h"
// #include "freertos/FreeRTOS.h"
// #include "freertos/task.h"
// #include "freertos/semphr.h"
// #include "lwip/err.h"
// #include "lwip/sys.h"
// #include "esp_mac.h"
// #include "driver/i2s_std.h"
// #include "driver/gpio.h"
// #include "esp_task_wdt.h"
// #include "esp_timer.h"
// #include "soc/i2s_struct.h"

// // WiFi configuration
// #define EXAMPLE_ESP_WIFI_SSID      "test_ssid"
// #define EXAMPLE_ESP_WIFI_PASS      "test_pass"
// #define EXAMPLE_MAX_STA_CONN       4

// // I2S configuration
// #define I2S_SAMPLE_RATE           24000
// #define I2S_BITS_PER_SAMPLE       I2S_BITS_PER_SAMPLE_32BIT
// #define I2S_DMA_BUF_COUNT         8
// #define I2S_DMA_BUF_LEN           128
// #define BUFFER_SIZE               8192 * 4

// static const char *TAG = "WiFi_AP_Audio_Stream";

// // Audio buffers with volatile qualifier
// static volatile uint16_t audio_bufferA1[BUFFER_SIZE/4];
// static volatile uint16_t audio_bufferA2[BUFFER_SIZE/4];
// static volatile uint16_t audio_bufferB1[BUFFER_SIZE/4];
// static volatile uint16_t audio_bufferB2[BUFFER_SIZE/4];
// static volatile uint16_t audio_bufferC1[BUFFER_SIZE / 4];
// static volatile uint16_t audio_bufferC2[BUFFER_SIZE / 4];
// static volatile uint16_t audio_bufferD1[BUFFER_SIZE / 4];
// static volatile uint16_t audio_bufferD2[BUFFER_SIZE / 4];
// size_t bufIndexA = 0;
// size_t bufIndexB = 0;
// static volatile bool buffer_sel = true;

// // Synchronization primitives
// //static SemaphoreHandle_t buffer_mutex = NULL;
// static volatile bool stream_active = false;

// // Forward declarations
// static void wifi_event_handler(void *arg, esp_event_base_t event_base, int32_t event_id, void *event_data);
// static esp_err_t wifi_init_softap(void);
// void setup_i2s(void);
// static esp_err_t ach1_handler(httpd_req_t *req);
// static void start_webserver(void);
// //static void i2s_sampling_task(void *arg);
// //static void wifi_task(void *arg);

// i2s_chan_handle_t rx_handle_0;
// i2s_chan_handle_t rx_handle_1;


// // WiFi event handler function
// static void wifi_event_handler(void *arg, esp_event_base_t event_base, int32_t event_id, void *event_data) {
//     if (event_id == WIFI_EVENT_AP_STACONNECTED) {
//         wifi_event_ap_staconnected_t *event = (wifi_event_ap_staconnected_t *)event_data;
//         ESP_LOGI(TAG, "Station "MACSTR" joined, AID=%d", MAC2STR(event->mac), event->aid);
//     } else if (event_id == WIFI_EVENT_AP_STADISCONNECTED) {
//         wifi_event_ap_stadisconnected_t *event = (wifi_event_ap_stadisconnected_t *)event_data;
//         ESP_LOGI(TAG, "Station "MACSTR" left, AID=%d", MAC2STR(event->mac), event->aid);
//     }
// }

// // WiFi initialization function
// static esp_err_t wifi_init_softap(void) {
//     esp_err_t ret;
    
//     ESP_LOGI(TAG, "Starting WiFi initialization...");
    
//     ret = esp_netif_init();
//     if (ret != ESP_OK) {
//         ESP_LOGE(TAG, "TCP/IP adapter initialization failed");
//         return ret;
//     }
//     ESP_LOGI(TAG, "TCP/IP adapter initialized");
    
//     ret = esp_event_loop_create_default();
//     if (ret != ESP_OK) {
//         ESP_LOGE(TAG, "Event loop creation failed");
//         return ret;
//     }
//     ESP_LOGI(TAG, "Event loop created");
    
//     esp_netif_t *ap_netif = esp_netif_create_default_wifi_ap();
//     if (ap_netif == NULL) {
//         ESP_LOGE(TAG, "Failed to create WiFi AP netif");
//         return ESP_FAIL;
//     }
//     ESP_LOGI(TAG, "WiFi AP netif created");
    
//     wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
//     ret = esp_wifi_init(&cfg);
//     if (ret != ESP_OK) {
//         ESP_LOGE(TAG, "WiFi initialization failed");
//         return ret;
//     }
//     ESP_LOGI(TAG, "WiFi initialized");
    
//     ret = esp_event_handler_instance_register(WIFI_EVENT, 
//                                             ESP_EVENT_ANY_ID, 
//                                             &wifi_event_handler, 
//                                             NULL, 
//                                             NULL);
//     if (ret != ESP_OK) {
//         ESP_LOGE(TAG, "Event handler registration failed");
//         return ret;
//     }
//     ESP_LOGI(TAG, "Event handler registered");
    
//     wifi_config_t wifi_config = {
//         .ap = {
//             .ssid = EXAMPLE_ESP_WIFI_SSID,
//             .ssid_len = strlen(EXAMPLE_ESP_WIFI_SSID),
//             .password = EXAMPLE_ESP_WIFI_PASS,
//             .max_connection = EXAMPLE_MAX_STA_CONN,
//             .authmode = strlen(EXAMPLE_ESP_WIFI_PASS) ? WIFI_AUTH_WPA_WPA2_PSK : WIFI_AUTH_OPEN
//         },
//     };
    
//     ret = esp_wifi_set_mode(WIFI_MODE_AP);
//     if (ret != ESP_OK) {
//         ESP_LOGE(TAG, "Failed to set WiFi mode");
//         return ret;
//     }
//     ESP_LOGI(TAG, "WiFi mode set to AP");
    
//     ret = esp_wifi_set_config(WIFI_IF_AP, &wifi_config);
//     if (ret != ESP_OK) {
//         ESP_LOGE(TAG, "Failed to set WiFi config");
//         return ret;
//     }
//     ESP_LOGI(TAG, "WiFi config set");
    
//     ret = esp_wifi_start();
//     if (ret != ESP_OK) {
//         ESP_LOGE(TAG, "Failed to start WiFi");
//         return ret;
//     }
//     ESP_LOGI(TAG, "WiFi started successfully");
    
//     return ESP_OK;
// }

// // I2S setup function
// #include "driver/i2s_std.h"
// #include "driver/gpio.h"

// void setup_i2s(void) {
//     ESP_LOGI("I2S", "Initializing I2S peripherals...");

//     // === Configure First I2S Peripheral (I2S_NUM_0) ===
//     i2s_chan_config_t chan_cfg_0 = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
//     if (i2s_new_channel(&chan_cfg_0, NULL, &rx_handle_0) != ESP_OK) {
//         ESP_LOGE("I2S", "Failed to create I2S RX channel 1");
//         return;
//     }

//     i2s_std_config_t std_cfg_0 = {
//         .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(I2S_SAMPLE_RATE),
//         .slot_cfg = I2S_STD_MSB_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_STEREO),
//         .gpio_cfg = {
//             .mclk = I2S_GPIO_UNUSED,
//             .bclk = GPIO_NUM_14,
//             .ws = GPIO_NUM_13,
//             .dout = I2S_GPIO_UNUSED,
//             .din = GPIO_NUM_21,
//             .invert_flags = {
//                 .mclk_inv = false,
//                 .bclk_inv = false,
//                 .ws_inv = false,
//             },
//         },
//     };

//     if (i2s_channel_init_std_mode(rx_handle_0, &std_cfg_0) != ESP_OK) {
//         ESP_LOGE("I2S", "Failed to initialize I2S RX channel 1");
//         return;
//     }

//     if (i2s_channel_enable(rx_handle_0) != ESP_OK) {
//         ESP_LOGE("I2S", "Failed to enable I2S RX channel 1");
//         return;
//     }

//     // === Configure Second I2S Peripheral (I2S_NUM_1) ===
//     i2s_chan_config_t chan_cfg_1 = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_1, I2S_ROLE_MASTER);
//     if (i2s_new_channel(&chan_cfg_1, NULL, &rx_handle_1) != ESP_OK) {
//         ESP_LOGE("I2S", "Failed to create I2S RX channel 2");
//         return;
//     }

//     i2s_std_config_t std_cfg_1 = {
//         .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(I2S_SAMPLE_RATE),
//         .slot_cfg = I2S_STD_MSB_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_STEREO),
//         .gpio_cfg = {
//             .mclk = I2S_GPIO_UNUSED,
//             .bclk = GPIO_NUM_41,
//             .ws = GPIO_NUM_42,
//             .dout = I2S_GPIO_UNUSED,
//             .din = GPIO_NUM_2,
//             .invert_flags = {
//                 .mclk_inv = false,
//                 .bclk_inv = false,
//                 .ws_inv = false,
//             },
//         },
//     };

//     if (i2s_channel_init_std_mode(rx_handle_1, &std_cfg_1) != ESP_OK) {
//         ESP_LOGE("I2S", "Failed to initialize I2S RX channel 2");
//         return;
//     }

//     if (i2s_channel_enable(rx_handle_1) != ESP_OK) {
//         ESP_LOGE("I2S", "Failed to enable I2S RX channel 2");
//         return;
//     }

//     ESP_LOGI("I2S", "I2S peripherals successfully initialized!");
// }


// // Start webserver function
// static void start_webserver(void) {
//     ESP_LOGI(TAG, "Starting webserver initialization...");
    
//     httpd_config_t config = HTTPD_DEFAULT_CONFIG();
//     config.stack_size = 8192 * 2;
//     config.task_priority = tskIDLE_PRIORITY + 5;
    
//     httpd_handle_t server = NULL;
    
//     ESP_LOGI(TAG, "Starting HTTP server on port: %d", config.server_port);
    
//     esp_err_t ret = httpd_start(&server, &config);
//     if (ret == ESP_OK) {
//         // URI handler structure for GET /audio_stream
//         httpd_uri_t audio_stream = {
//             .uri       = "/ach1",
//             .method    = HTTP_GET,
//             .handler   = ach1_handler,
//             .user_ctx  = NULL
//         };
        
//         // Register URI handlers
//         ret = httpd_register_uri_handler(server, &audio_stream);
//         if (ret == ESP_OK) {
//             ESP_LOGI(TAG, "URI handler registered successfully");
//         } else {
//             ESP_LOGE(TAG, "Failed to register URI handler: %s", esp_err_to_name(ret));
//         }
//     } else {
//         ESP_LOGE(TAG, "Failed to start server: %s", esp_err_to_name(ret));
//     }
// }

// void app_main(void) {
//     ESP_LOGI(TAG, "Starting application...");
    
//     // Initialize NVS
//     esp_err_t ret = nvs_flash_init();
//     if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
//         ESP_ERROR_CHECK(nvs_flash_erase());
//         ret = nvs_flash_init();
//     }
//     ESP_ERROR_CHECK(ret);
//     ESP_LOGI(TAG, "NVS initialized");
        
//     ESP_LOGI(TAG, "Initializing WiFi in SoftAP Mode");
    
//     // Initialize WiFi
//     ret = wifi_init_softap();
//     if (ret != ESP_OK) {
//         ESP_LOGE(TAG, "WiFi initialization failed");
//         vTaskDelete(NULL);
//         return;
//     }
//     ESP_LOGI(TAG, "WiFi Initilization Successful");

//     // Give some time for WiFi to initialize
//     //vTaskDelay(pdMS_TO_TICKS(1000));
    
//     ESP_LOGI(TAG, "Starting webserver");
//     // Start webserver
//     start_webserver();
//     ESP_LOGI(TAG, "Webserver initialization Successfully");
    
//     ESP_LOGI(TAG, "WiFi task completed initialization");

//     // Initialize I2S
//     setup_i2s();
    
//     ESP_LOGI(TAG, "Application initialization completed");
// }

// // static esp_err_t ach1_handler(httpd_req_t *req) {
// //     ESP_LOGI(TAG, "Audio handler started");
// //     esp_err_t res = ESP_OK;
    
// //     // Set response type and headers
// //     if ((res = httpd_resp_set_type(req, "audio/raw")) != ESP_OK) {
// //         ESP_LOGE(TAG, "Failed to set response type: %s", esp_err_to_name(res));
// //         goto cleanup;
// //     }
    
// //     if ((res = httpd_resp_set_hdr(req, "X-Audio-Sample-Rate", "24000")) != ESP_OK ||
// //         (res = httpd_resp_set_hdr(req, "X-Audio-Bits-Per-Sample", "16")) != ESP_OK ||
// //         (res = httpd_resp_set_hdr(req, "X-Audio-Channels", "4")) != ESP_OK) {  // Changed to 4 channels
// //         ESP_LOGE(TAG, "Failed to set audio headers: %s", esp_err_to_name(res));
// //         goto cleanup;
// //     }

// //     size_t bytes_read = 0;
// //     uint32_t raw_sample_0[2];  // Buffer for I2S_NUM_0 (mics 1 & 2)
// //     uint32_t raw_sample_1[2];  // Buffer for I2S_NUM_1 (mics 3 & 4)
    
// //     // Create a combined buffer for all 4 mics to send together
// //     uint16_t combined_buffer_A[BUFFER_SIZE];
// //     uint16_t combined_buffer_B[BUFFER_SIZE];
    
// //     while (true) {
// //         if (httpd_req_to_sockfd(req) < 0) {
// //             ESP_LOGI(TAG, "Client disconnected");
// //             goto cleanup;
// //         }
        
// //         // Read from both I2S peripherals and interleave the data
// //         if (buffer_sel) { // Buffer A
// //             for (bufIndexA = 0; bufIndexA < BUFFER_SIZE/4; bufIndexA++) {
// //                 // Read from first I2S peripheral (mics 1 & 2)
// //                 if (i2s_channel_read(rx_handle_0, raw_sample_0, sizeof(raw_sample_0), &bytes_read, portMAX_DELAY) == ESP_OK) {
// //                     audio_bufferA1[bufIndexA] = (uint16_t)((raw_sample_0[0] & 0xFFFF000) >> 12);
// //                     audio_bufferA2[bufIndexA] = (uint16_t)((raw_sample_0[1] & 0xFFFF000) >> 12);
                    
// //                     // Fill the first half of the combined buffer with interleaved data
// //                     combined_buffer_A[bufIndexA*4] = audio_bufferA1[bufIndexA];     // Mic 1
// //                     combined_buffer_A[bufIndexA*4 + 1] = audio_bufferA2[bufIndexA]; // Mic 2
// //                 }
                
// //                 // Read from second I2S peripheral (mics 3 & 4)
// //                 if (i2s_channel_read(rx_handle_1, raw_sample_1, sizeof(raw_sample_1), &bytes_read, portMAX_DELAY) == ESP_OK) {
// //                     audio_bufferC1[bufIndexA] = (uint16_t)((raw_sample_1[0] & 0xFFFF000) >> 12);
// //                     audio_bufferC2[bufIndexA] = (uint16_t)((raw_sample_1[1] & 0xFFFF000) >> 12);
                    
// //                     // Complete the interleaved data with the other two mics
// //                     combined_buffer_A[bufIndexA*4 + 2] = audio_bufferC1[bufIndexA]; // Mic 3
// //                     combined_buffer_A[bufIndexA*4 + 3] = audio_bufferC2[bufIndexA]; // Mic 4
// //                 }
// //             }
            
// //             // Send the combined buffer
// //             res = httpd_resp_send_chunk(req, (const char *)combined_buffer_A, BUFFER_SIZE * sizeof(uint16_t));
// //             bufIndexA = 0;
// //             buffer_sel = false;
// //         } else { // Buffer B
// //             for (bufIndexB = 0; bufIndexB < BUFFER_SIZE/4; bufIndexB++) {
// //                 // Read from first I2S peripheral (mics 1 & 2)
// //                 if (i2s_channel_read(rx_handle_0, raw_sample_0, sizeof(raw_sample_0), &bytes_read, portMAX_DELAY) == ESP_OK) {
// //                     audio_bufferB1[bufIndexB] = (uint16_t)((raw_sample_0[0] & 0xFFFF000) >> 12);
// //                     audio_bufferB2[bufIndexB] = (uint16_t)((raw_sample_0[1] & 0xFFFF000) >> 12);
                    
// //                     // Fill the combined buffer with interleaved data
// //                     combined_buffer_B[bufIndexB*4] = audio_bufferB1[bufIndexB];     // Mic 1
// //                     combined_buffer_B[bufIndexB*4 + 1] = audio_bufferB2[bufIndexB]; // Mic 2
// //                 }
                
// //                 // Read from second I2S peripheral (mics 3 & 4)
// //                 if (i2s_channel_read(rx_handle_1, raw_sample_1, sizeof(raw_sample_1), &bytes_read, portMAX_DELAY) == ESP_OK) {
// //                     audio_bufferD1[bufIndexB] = (uint16_t)((raw_sample_1[0] & 0xFFFF000) >> 12);
// //                     audio_bufferD2[bufIndexB] = (uint16_t)((raw_sample_1[1] & 0xFFFF000) >> 12);
                    
// //                     // Complete the interleaved data with the other two mics
// //                     combined_buffer_B[bufIndexB*4 + 2] = audio_bufferD1[bufIndexB]; // Mic 3
// //                     combined_buffer_B[bufIndexB*4 + 3] = audio_bufferD2[bufIndexB]; // Mic 4
// //                 }
// //             }
            
// //             // Send the combined buffer
// //             res = httpd_resp_send_chunk(req, (const char *)combined_buffer_B, BUFFER_SIZE * sizeof(uint16_t));
// //             bufIndexB = 0;
// //             buffer_sel = true;
// //         }
        
// //         if (res != ESP_OK) {
// //             ESP_LOGE(TAG, "Failed to send chunk: %s", esp_err_to_name(res));
// //             goto cleanup;
// //         }
// //     }

// // cleanup:
// //     return res;
// // }

// //ach1_handler pre change (before accomodating mics 3 and 4)
// static esp_err_t ach1_handler(httpd_req_t *req) {
//     ESP_LOGI(TAG, "Audio handler started");
//     esp_err_t res = ESP_OK;
    
//         // Set response type and headers
//     if ((res = httpd_resp_set_type(req, "audio/raw")) != ESP_OK) {
//         ESP_LOGE(TAG, "Failed to set response type: %s", esp_err_to_name(res));
//         goto cleanup;
//     }
    
//     if ((res = httpd_resp_set_hdr(req, "X-Audio-Sample-Rate", "24000")) != ESP_OK ||
//         (res = httpd_resp_set_hdr(req, "X-Audio-Bits-Per-Sample", "16")) != ESP_OK ||
//         (res = httpd_resp_set_hdr(req, "X-Audio-Channels", "2")) != ESP_OK) {
//         ESP_LOGE(TAG, "Failed to set audio headers: %s", esp_err_to_name(res));
//         goto cleanup;
//     }

//     // Add timing statistics
//     uint64_t last_print = 0;
//     uint32_t chunks_sent = 0;
//     //uint64_t start_time = esp_timer_get_time();
//     size_t bytes_read = 0;
//     uint32_t raw_sample[2];  // Buffer to hold raw left and right samples
    
//     while (true) {
//         if (httpd_req_to_sockfd(req) < 0) {
//             ESP_LOGI(TAG, "Client disconnected");
//             goto cleanup;
//         }

//         //uint64_t before_i2s = esp_timer_get_time();
        
//         // Read from I2S
//         if (buffer_sel) { // Buffer A
//             for (bufIndexA = 0; bufIndexA < BUFFER_SIZE/2; bufIndexA += 1) {
//                 if (i2s_channel_read(rx_handle_0, raw_sample, sizeof(raw_sample), &bytes_read, portMAX_DELAY) == ESP_OK) {
//                     audio_bufferA1[bufIndexA] = (uint16_t)((raw_sample[0] & 0xFFFF000) >> 12);
//                     audio_bufferA2[bufIndexA] = (uint16_t)((raw_sample[1] & 0xFFFF000) >> 12);
//                 }
//             }
//             res = httpd_resp_send_chunk(req, (const char *)audio_bufferA1, BUFFER_SIZE/2 * sizeof(uint16_t));
//             bufIndexA = 0;

//             buffer_sel = false;

//         }else{ //Buffer B
//             for (bufIndexB = 0; bufIndexB < BUFFER_SIZE/2; bufIndexB += 1) {
//                 if (i2s_channel_read(rx_handle_0, raw_sample, sizeof(raw_sample), &bytes_read, portMAX_DELAY) == ESP_OK) {
//                     audio_bufferB1[bufIndexB] = (uint16_t)((raw_sample[0] & 0xFFFF000) >> 12);
//                     audio_bufferB2[bufIndexB] = (uint16_t)((raw_sample[1] & 0xFFFF000) >> 12);
//                 }
//             }
//             res = httpd_resp_send_chunk(req, (const char *)audio_bufferB1, BUFFER_SIZE/2 * sizeof(uint16_t));
//             bufIndexB = 0;

//             buffer_sel = true;
            
//         }
        
//         if (res != ESP_OK) {
//             ESP_LOGE(TAG, "Failed to send chunk: %s", esp_err_to_name(res));
//             goto cleanup;
//         }
//     }

// cleanup:
//     return res;
// }


/*
 This setup_i2s function worked before
void setup_i2s(void) {
    // Define the I2S channel configuration for RX
    i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_AUTO, I2S_ROLE_MASTER);

    // Allocate the RX channel
    if (i2s_new_channel(&chan_cfg, NULL, &rx_handle) != ESP_OK) {
        ESP_LOGE("I2S", "Failed to create I2S RX channel");
        return;
    }

    // Configure the standard I2S settings
    i2s_std_config_t std_cfg = {
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
    if (i2s_channel_init_std_mode(rx_handle, &std_cfg) != ESP_OK) {
        ESP_LOGE("I2S", "Failed to initialize I2S RX channel in standard mode");
        return;
    }

    // Enable the RX channel to start receiving data
    if (i2s_channel_enable(rx_handle) != ESP_OK) {
        ESP_LOGE("I2S", "Failed to enable I2S RX channel");
    }

    //i2s_channel_enable(rx_handle);
}

*/






// #include <stdio.h>
// #include <stdint.h>
// #include <stdlib.h>
// #include "esp_log.h"
// #include "driver/i2s_std.h"
// #include "gpio.h"
// #include "freertos/FreeRTOS.h"
// #include "freertos/task.h"

// // WiFi includes
// #include "esp_wifi.h"
// #include "esp_event.h"
// #include "esp_netif.h"
// #include "lwip/err.h"
// #include "lwip/sys.h"

// // WiFi configuration
// #define EXAMPLE_ESP_WIFI_SSID      "test_ssid"
// #define EXAMPLE_ESP_WIFI_PASS      "test_pass"
// #define EXAMPLE_MAX_STA_CONN       4

// // I2S configuration
// #define I2S_SAMPLE_RATE     24000
// #define I2S_BITS_PER_SAMPLE I2S_BITS_PER_SAMPLE_32BIT
// #define I2S_DMA_BUF_COUNT   8
// #define I2S_DMA_BUF_LEN     64
// #define BUFFER_SIZE         1024

// static const char *TAG = "I2S_AUDIO";

// // Double buffers for I2S data
// volatile uint16_t i2s_bufferA[BUFFER_SIZE];
// volatile uint16_t i2s_bufferB[BUFFER_SIZE];
// volatile bool buffer_flag0 = false;
// volatile bool buffer_flag1 = false;

// // I2S Handle
// i2s_chan_handle_t i2s0_rx_handle;
// i2s_chan_handle_t i2s1_rx_handle;

// //function definitions
// void setup_four_i2s_mics();
// static esp_err_t wifi_init_softap(void);
// static void wifi_event_handler(void *arg, esp_event_base_t event_base, int32_t event_id, void *event_data);
// static esp_err_t ach1_handler(httpd_req_t *req);

// void app_main(void)
// {

//     // init i2s setup for four mics (two i2s peripherals)
//     setup_four_i2s_mics(); 


//     while (1) {
//         vTaskDelay(pdMS_TO_TICKS(50));  // Keep task running
//     }
// }


// void setup_four_i2s_mics()
// {
//         /* Begin Configuring I2S0 */

//         // Define the I2S channel configuration for RX
//         i2s_chan_config_t chan_cfg0 = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_AUTO, I2S_ROLE_MASTER);

//         // Allocate the RX channel
//         if (i2s_new_channel(&chan_cfg0, NULL, &i2s0_rx_handle) != ESP_OK) {
//             ESP_LOGE("I2S", "Failed to create I2S0 RX channel");
//             return;
//         }
    
//         // Configure the standard I2S settings
//         i2s_std_config_t std_cfg0 = {
//             .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(I2S_SAMPLE_RATE),
//             .slot_cfg = I2S_STD_MSB_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_STEREO),
//             .gpio_cfg = {
//                 .mclk = I2S_GPIO_UNUSED,
//                 .bclk = GPIO_NUM_14,
//                 .ws = GPIO_NUM_13,
//                 .dout = I2S_GPIO_UNUSED,
//                 .din = GPIO_NUM_21,
//                 .invert_flags = {
//                     .mclk_inv = false,
//                     .bclk_inv = false,
//                     .ws_inv = false,
//                 },
//             },
//         };
    
//         // Initialize the RX channel in standard mode
//         if (i2s_channel_init_std_mode(i2s0_rx_handle, &std_cfg0) != ESP_OK) {
//             ESP_LOGE("I2S", "Failed to initialize I2S0 RX channel in standard mode");
//             return;
//         }
    
//         // Enable the RX channel to start receiving data
//         if (i2s_channel_enable(i2s0_rx_handle) != ESP_OK) {
//             ESP_LOGE("I2S", "Failed to enable I2S0 RX channel");
//         }

//         /* End Configuring I2S0 */

//             // I2S1 pins configuration
//     // i2s_pin_config_t pin_config1 = {
//     //     .bck_io_num = GPIO_NUM_33,
//     //     .ws_io_num = GPIO_NUM_25,
//     //     .data_out_num = I2S_PIN_NO_CHANGE,
//     //     .data_in_num = GPIO_NUM_32
//     // };

// }


// // WiFi initialization function
// static esp_err_t wifi_init_softap(void) {
//     esp_err_t ret;
    
//     ESP_LOGI(TAG, "Starting WiFi initialization...");
    
//     ret = esp_netif_init();
//     if (ret != ESP_OK) {
//         ESP_LOGE(TAG, "TCP/IP adapter initialization failed");
//         return ret;
//     }
//     ESP_LOGI(TAG, "TCP/IP adapter initialized");
    
//     ret = esp_event_loop_create_default();
//     if (ret != ESP_OK) {
//         ESP_LOGE(TAG, "Event loop creation failed");
//         return ret;
//     }
//     ESP_LOGI(TAG, "Event loop created");
    
//     esp_netif_t *ap_netif = esp_netif_create_default_wifi_ap();
//     if (ap_netif == NULL) {
//         ESP_LOGE(TAG, "Failed to create WiFi AP netif");
//         return ESP_FAIL;
//     }
//     ESP_LOGI(TAG, "WiFi AP netif created");
    
//     wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
//     ret = esp_wifi_init(&cfg);
//     if (ret != ESP_OK) {
//         ESP_LOGE(TAG, "WiFi initialization failed");
//         return ret;
//     }
//     ESP_LOGI(TAG, "WiFi initialized");
    
//     ret = esp_event_handler_instance_register(WIFI_EVENT, 
//                                             ESP_EVENT_ANY_ID, 
//                                             &wifi_event_handler, 
//                                             NULL, 
//                                             NULL);
//     if (ret != ESP_OK) {
//         ESP_LOGE(TAG, "Event handler registration failed");
//         return ret;
//     }
//     ESP_LOGI(TAG, "Event handler registered");
    
//     wifi_config_t wifi_config = {
//         .ap = {
//             .ssid = EXAMPLE_ESP_WIFI_SSID,
//             .ssid_len = strlen(EXAMPLE_ESP_WIFI_SSID),
//             .password = EXAMPLE_ESP_WIFI_PASS,
//             .max_connection = EXAMPLE_MAX_STA_CONN,
//             .authmode = strlen(EXAMPLE_ESP_WIFI_PASS) ? WIFI_AUTH_WPA_WPA2_PSK : WIFI_AUTH_OPEN
//         },
//     };
    
//     ret = esp_wifi_set_mode(WIFI_MODE_AP);
//     if (ret != ESP_OK) {
//         ESP_LOGE(TAG, "Failed to set WiFi mode");
//         return ret;
//     }
//     ESP_LOGI(TAG, "WiFi mode set to AP");
    
//     ret = esp_wifi_set_config(WIFI_IF_AP, &wifi_config);
//     if (ret != ESP_OK) {
//         ESP_LOGE(TAG, "Failed to set WiFi config");
//         return ret;
//     }
//     ESP_LOGI(TAG, "WiFi config set");
    
//     ret = esp_wifi_start();
//     if (ret != ESP_OK) {
//         ESP_LOGE(TAG, "Failed to start WiFi");
//         return ret;
//     }
//     ESP_LOGI(TAG, "WiFi started successfully");
    
//     return ESP_OK;
// }

// // WiFi event handler function
// static void wifi_event_handler(void *arg, esp_event_base_t event_base, int32_t event_id, void *event_data) {
//     if (event_id == WIFI_EVENT_AP_STACONNECTED) {
//         wifi_event_ap_staconnected_t *event = (wifi_event_ap_staconnected_t *)event_data;
//         ESP_LOGI(TAG, "Station "MACSTR" joined, AID=%d", MAC2STR(event->mac), event->aid);
//     } else if (event_id == WIFI_EVENT_AP_STADISCONNECTED) {
//         wifi_event_ap_stadisconnected_t *event = (wifi_event_ap_stadisconnected_t *)event_data;
//         ESP_LOGI(TAG, "Station "MACSTR" left, AID=%d", MAC2STR(event->mac), event->aid);
//     }
// }

// // Start webserver function
// static void start_webserver(void) {
//     ESP_LOGI(TAG, "Starting webserver initialization...");
    
//     httpd_config_t config = HTTPD_DEFAULT_CONFIG();
//     config.stack_size = 8192 * 2;
//     config.task_priority = tskIDLE_PRIORITY + 5;
    
//     httpd_handle_t server = NULL;
    
//     ESP_LOGI(TAG, "Starting HTTP server on port: %d", config.server_port);
    
//     esp_err_t ret = httpd_start(&server, &config);
//     if (ret == ESP_OK) {
//         // URI handler structure for GET /audio_stream
//         httpd_uri_t audio_stream = {
//             .uri       = "/ach1",
//             .method    = HTTP_GET,
//             .handler   = ach1_handler,
//             .user_ctx  = NULL
//         };
        
//         // Register URI handlers
//         ret = httpd_register_uri_handler(server, &audio_stream);
//         if (ret == ESP_OK) {
//             ESP_LOGI(TAG, "URI handler registered successfully");
//         } else {
//             ESP_LOGE(TAG, "Failed to register URI handler: %s", esp_err_to_name(ret));
//         }
//     } else {
//         ESP_LOGE(TAG, "Failed to start server: %s", esp_err_to_name(ret));
//     }
// }
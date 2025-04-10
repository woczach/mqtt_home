#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>     // For usleep()
#include <signal.h>     // For signal handling
#include <errno.h>

#include <curl/curl.h>  // For HTTP requests
#include "cJSON.h"      // For JSON parsing (make sure libcjson-dev is installed)
#include "led-matrix-c.h" // C API for the matrix library

// --- Configuration Constants ---
const int MATRIX_ROWS = 32;
const int MATRIX_COLS = 64;
const int MATRIX_CHAIN = 1;
const int MATRIX_PARALLEL = 1;
const int MATRIX_BRIGHTNESS = 50;
const char* HARDWARE_MAPPING = "adafruit-hat";
// Adjust FONT_PATH relative to where you compile/run, or use an absolute path
const char* FONT_PATH = "../rpi-rgb-led-matrix/fonts/6x10.bdf"; // Common relative path

// --- REPLACE WITH YOUR INFLUXDB v1.x DETAILS ---
const char* INFLUXDB_URL = "http://192.168.0.230:8086";
const char* INFLUXDB_DATABASE = "heat";
const char* INFLUXDB_USER = ""; // Optional
const char* INFLUXDB_PASSWORD = ""; // Optional
const char* INFLUXQL_QUERY = "SELECT \"value\" FROM \"esp/sypialnia\" ORDER BY time DESC LIMIT 1"; // Fetch only 1 value

// --- Global variable for signal handling ---
volatile sig_atomic_t interrupt_received = 0; // Use sig_atomic_t for signal safety

// --- Struct to hold Curl response data ---
struct MemoryStruct {
  char *memory;
  size_t size;
};

// --- Curl Write Callback Function ---
static size_t WriteMemoryCallback(void *contents, size_t size, size_t nmemb, void *userp) {
    size_t realsize = size * nmemb;
    struct MemoryStruct *mem = (struct MemoryStruct *)userp;

    // Expand buffer using realloc
    char *ptr = realloc(mem->memory, mem->size + realsize + 1);
    if(ptr == NULL) {
        /* out of memory! */
        fprintf(stderr, "Error: not enough memory (realloc returned NULL)\n");
        return 0; // Signal error to curl
    }

    mem->memory = ptr;
    memcpy(&(mem->memory[mem->size]), contents, realsize);
    mem->size += realsize;
    mem->memory[mem->size] = 0; // Null-terminate the buffer

    return realsize; // Tell curl how many bytes we handled
}

// --- Signal Handler Function ---
static void InterruptHandler(int signo) {
    (void)signo; // Prevent unused parameter warning
    interrupt_received = 1; // Set the flag
}

// --- Main Function ---
int main(int argc, char *argv[]) {
    struct RGBLedMatrixOptions matrix_options;
    struct RGBLedMatrix *matrix = NULL;
    struct LedCanvas *offscreen_canvas = NULL;
    struct LedFont *font = NULL;
    char time_str[100]; // Buffer for formatted time
    char influx_value_str[100] = "Loading..."; // Buffer for InfluxDB value, default text
    int x_pos = 2;
    int y_pos = 0; // Will be set after font loading

    // --- 1. Configure Matrix Options ---
    // Use memset to initialize options struct to zeros/NULLs
    memset(&matrix_options, 0, sizeof(matrix_options));
    matrix_options.rows = MATRIX_ROWS;
    matrix_options.cols = MATRIX_COLS;
    matrix_options.chain_length = MATRIX_CHAIN;
    matrix_options.parallel = MATRIX_PARALLEL;
    matrix_options.brightness = MATRIX_BRIGHTNESS;
    matrix_options.hardware_mapping = HARDWARE_MAPPING;
    matrix_options.limit_refresh_rate_hz = 75;
    matrix_options.show_refresh_rate = 0; // 1 to enable
    // matrix_options.pwm_lsb_nanoseconds = 130; // Example
    // IMPORTANT: runtime_options equivalent (drop_privileges) is handled internally
    // by the C API or is less commonly needed. Assume default behavior.

    // --- 2. Create Matrix Object ---
    // Note: The C API might require root privileges depending on the hardware mapping.
    matrix = led_matrix_create_from_options(&matrix_options, &argc, &argv);
    if (matrix == NULL) {
        fprintf(stderr, "Error: Failed to create matrix object. %s. Did you run with sudo? Correct hardware_mapping?\n", strerror(errno));
        return 1;
    }
    printf("Matrix object created.\n");

    // --- 3. Create Offscreen Canvas ---
    // Canvas is associated with the matrix and cleaned up when matrix is deleted.
    offscreen_canvas = led_matrix_create_offscreen_canvas(matrix);
    if (offscreen_canvas == NULL) {
        fprintf(stderr, "Error: Failed to create offscreen canvas.\n");
        led_matrix_delete(matrix);
        return 1;
    }

    // --- 4. Load Font ---
    font = load_font(FONT_PATH);
    if (font == NULL) {
        fprintf(stderr, "Error: Couldn't load font '%s'\n", FONT_PATH);
        // No need to delete canvas explicitly, led_matrix_delete handles it
        led_matrix_delete(matrix);
        return 1;
    }
    printf("Font loaded.\n");

    // --- 5. Define Colors and Position ---
    struct Color text_color = {0, 0, 255}; // Blue text
    struct Color bg_color = {0, 0, 0};     // Black background
    y_pos = font->baseline; // Position text baseline correctly

    // --- 6. Setup Signal Handler ---
    signal(SIGTERM, InterruptHandler);
    signal(SIGINT, InterruptHandler);

    // --- 7. Initial Display (Optional "Hello") ---
    led_canvas_fill(offscreen_canvas, bg_color.r, bg_color.g, bg_color.b);
    // draw_text(offscreen_canvas, font, x_pos, y_pos, text_color.r, text_color.g, text_color.b, "Hello C!", 0);
    // offscreen_canvas = led_matrix_swap_on_vsync(matrix, offscreen_canvas);
    // printf("Initial text drawn.\n");

    // --- 8. Setup Curl ---
    CURL *curl_handle;
    CURLcode res;
    struct MemoryStruct chunk; // Struct to hold response

    curl_global_init(CURL_GLOBAL_ALL);

    // --- 9. Main Loop ---
    printf("Starting display loop. Press Ctrl+C to exit.\n");
    while (!interrupt_received) {
        // --- 9a. Get InfluxDB Data ---
        chunk.memory = malloc(1);  // Start with 1 byte, will be grown by realloc
        chunk.size = 0;            // No data yet
        if(chunk.memory == NULL) {
            fprintf(stderr, "Error: Failed to allocate initial memory for curl buffer.\n");
            // Skip this update cycle
        } else {
            curl_handle = curl_easy_init();
            if(curl_handle) {
                char *escaped_db = curl_easy_escape(curl_handle, INFLUXDB_DATABASE, 0);
                char *escaped_query = curl_easy_escape(curl_handle, INFLUXQL_QUERY, 0);
                char *escaped_user = NULL;
                char *escaped_pass = NULL;
                char full_url[1024]; // Ensure this is large enough
                int url_len = 0;

                if (!escaped_db || !escaped_query) {
                     fprintf(stderr, "Error: Failed to URL-encode parameters.\n");
                     curl_free(escaped_db); // curl_free handles NULL safely
                     curl_free(escaped_query);
                     curl_easy_cleanup(curl_handle);
                     free(chunk.memory); // Free the buffer allocated for this cycle
                     chunk.memory = NULL; // Avoid double free later
                } else {
                    url_len = snprintf(full_url, sizeof(full_url), "%s/query?db=%s&q=%s",
                                     INFLUXDB_URL, escaped_db, escaped_query);

                    // Add optional authentication
                    if (INFLUXDB_USER && INFLUXDB_USER[0] != '\0') {
                        escaped_user = curl_easy_escape(curl_handle, INFLUXDB_USER, 0);
                        escaped_pass = curl_easy_escape(curl_handle, INFLUXDB_PASSWORD, 0);
                        if(escaped_user && escaped_pass) {
                             url_len += snprintf(full_url + url_len, sizeof(full_url) - url_len, "&u=%s&p=%s",
                                                 escaped_user, escaped_pass);
                        } else {
                             fprintf(stderr, "Warning: Failed to URL-encode username/password.\n");
                             // Proceed without auth if encoding failed
                        }
                    }

                    if (url_len >= sizeof(full_url)) {
                         fprintf(stderr, "Error: Constructed URL is too long!\n");
                    } else {
                        // printf("Query URL: %s\n", full_url); // Debugging (careful with password)
                        curl_easy_setopt(curl_handle, CURLOPT_URL, full_url);
                        curl_easy_setopt(curl_handle, CURLOPT_HTTPGET, 1L);
                        curl_easy_setopt(curl_handle, CURLOPT_WRITEFUNCTION, WriteMemoryCallback);
                        curl_easy_setopt(curl_handle, CURLOPT_WRITEDATA, (void *)&chunk);
                        curl_easy_setopt(curl_handle, CURLOPT_TIMEOUT, 10L); // 10 seconds timeout
                        // curl_easy_setopt(curl_handle, CURLOPT_VERBOSE, 1L); // Uncomment for curl debug info

                        res = curl_easy_perform(curl_handle);

                        if(res != CURLE_OK) {
                            fprintf(stderr, "curl_easy_perform() failed: %s\n", curl_easy_strerror(res));
                            strncpy(influx_value_str, "Curl Err", sizeof(influx_value_str) - 1);
                            influx_value_str[sizeof(influx_value_str) - 1] = '\0'; // Ensure null termination
                        } else {
                            long http_code = 0;
                            curl_easy_getinfo(curl_handle, CURLINFO_RESPONSE_CODE, &http_code);
                            // printf("HTTP Response Code: %ld\n", http_code);
                            // printf("Response Body:\n%s\n", chunk.memory ? chunk.memory : "<empty>");

                            if (http_code == 200 && chunk.memory) {
                                // --- 9b. Parse JSON ---
                                cJSON *json = cJSON_Parse(chunk.memory);
                                if (json == NULL) {
                                    const char *error_ptr = cJSON_GetErrorPtr();
                                    if (error_ptr != NULL) {
                                        fprintf(stderr, "Error parsing JSON before: %s\n", error_ptr);
                                    } else {
                                        fprintf(stderr, "Error parsing JSON.\n");
                                    }
                                    strncpy(influx_value_str, "JSON Err", sizeof(influx_value_str) - 1);
                                    influx_value_str[sizeof(influx_value_str) - 1] = '\0';
                                } else {
                                    const cJSON *results = cJSON_GetObjectItemCaseSensitive(json, "results");
                                    const cJSON *firstResult = (cJSON_IsArray(results) && cJSON_GetArraySize(results) > 0) ? cJSON_GetArrayItem(results, 0) : NULL;
                                    const cJSON *series = cJSON_GetObjectItemCaseSensitive(firstResult, "series");
                                    const cJSON *firstSeries = (cJSON_IsArray(series) && cJSON_GetArraySize(series) > 0) ? cJSON_GetArrayItem(series, 0) : NULL;
                                    const cJSON *values = cJSON_GetObjectItemCaseSensitive(firstSeries, "values");
                                    const cJSON *firstValueRow = (cJSON_IsArray(values) && cJSON_GetArraySize(values) > 0) ? cJSON_GetArrayItem(values, 0) : NULL;
                                    // Value should be the second element (index 1) in the row [timestamp, value]
                                    const cJSON *value = (cJSON_IsArray(firstValueRow) && cJSON_GetArraySize(firstValueRow) > 1) ? cJSON_GetArrayItem(firstValueRow, 1) : NULL;

                                    if (cJSON_IsNumber(value)) {
                                        // Format the number to string - adjust precision as needed
                                        snprintf(influx_value_str, sizeof(influx_value_str), "%.1f", value->valuedouble);
                                    } else if (cJSON_IsString(value)) {
                                        // Handle string values if necessary
                                         snprintf(influx_value_str, sizeof(influx_value_str), "%.6s", value->valuestring); // Limit length
                                    } else {
                                         // Couldn't find value in the expected structure
                                         fprintf(stderr, "Warning: Could not find value in JSON structure.\n");
                                         strncpy(influx_value_str, "No Data", sizeof(influx_value_str) - 1);
                                         influx_value_str[sizeof(influx_value_str) - 1] = '\0';
                                    }
                                    cJSON_Delete(json); // Free parsed JSON object
                                }
                            } else {
                                fprintf(stderr, "InfluxDB query failed. HTTP Status: %ld\n", http_code);
                                strncpy(influx_value_str, "HTTP Err", sizeof(influx_value_str) - 1);
                                influx_value_str[sizeof(influx_value_str) - 1] = '\0';
                                // Optionally print response body for debugging:
                                // fprintf(stderr, "Response Body:\n%s\n", chunk.memory ? chunk.memory : "<empty>");
                            }
                        }
                    }
                    // Cleanup URL encoded strings
                    curl_free(escaped_db);
                    curl_free(escaped_query);
                    curl_free(escaped_user); // Safe even if NULL
                    curl_free(escaped_pass); // Safe even if NULL
                }
                curl_easy_cleanup(curl_handle);
            } else {
                 fprintf(stderr, "Error: Failed to initialize curl handle.\n");
                 strncpy(influx_value_str, "Curl Init", sizeof(influx_value_str) - 1);
                 influx_value_str[sizeof(influx_value_str) - 1] = '\0';
            }

            // Free the memory allocated by the callback
            free(chunk.memory);
        } // end if(chunk.memory != NULL)

        // --- 9c. Get Current Time ---
        time_t now = time(NULL);
        struct tm *local_time = localtime(&now);
        strftime(time_str, sizeof(time_str), "%H:%M:%S", local_time);

        // --- 9d. Update Display ---
        led_canvas_fill(offscreen_canvas, bg_color.r, bg_color.g, bg_color.b);

        // Draw Time
        draw_text(offscreen_canvas, font, x_pos, y_pos, text_color.r, text_color.g, text_color.b, time_str, 0);

        // Draw InfluxDB Value (on a second line, adjust y_pos)
        int y2_pos = y_pos + font->height + 1; // Position below the time
        draw_text(offscreen_canvas, font, x_pos, y2_pos, text_color.r, text_color.g, text_color.b, influx_value_str, 0);

        // Swap buffer to display
        offscreen_canvas = led_matrix_swap_on_vsync(matrix, offscreen_canvas);

        // --- 9e. Wait ---
        // Sleep for a while before the next update.
        // usleep takes microseconds (5 seconds = 5,000,000 microseconds)
        usleep(5 * 1000 * 1000); // 5 seconds

    } // End while loop

    // --- 10. Cleanup ---
    printf("\nCaught interrupt signal. Cleaning up...\n");
    curl_global_cleanup();

    if (matrix) {
        led_matrix_clear(matrix); // Clear the display
        // No need to delete canvas explicitly if created with led_matrix_create_offscreen_canvas
        led_matrix_delete(matrix); // Deletes matrix and associated canvas
    }
    // Font does not seem to have a dedicated delete function in the C API examples,
    // assume it's managed differently or doesn't need explicit deletion.
    // If using a different font loading mechanism, check its cleanup requirements.

    printf("Exiting.\n");
    return 0;
}
#include <iostream>
#include <string>
#include <vector>
#include <ctime>

#include <curl/curl.h> // For HTTP requests
#include "json.hpp"
using json = nlohmann::json;
#include <sstream>
#include "led-matrix.h" // Main matrix header - Needed for RGBMatrix, Options, etc.
#include "graphics.h"   // Graphics utilities - Needed for Color, Font, DrawText
#include <unistd.h>     // For the sleep() function
#include <csignal>      // For signal handling (SIGINT, SIGTERM)

// --- Configuration Constants ---
const int MATRIX_ROWS = 32;          // Height of your panel
const int MATRIX_COLS = 64;          // Width of your panel
const int MATRIX_CHAIN = 1;          // Number of panels chained horizontally
const int MATRIX_PARALLEL = 1;       // Number of panel rows (usually 1)
const int MATRIX_BRIGHTNESS = 50;    // Brightness (0-100), start low!
const char* HARDWARE_MAPPING = "adafruit-hat"; // Hardware mapping string (MUST match your HAT & build)
const char* FONT_PATH = "/home/p/rpi-rgb-led-matrix/fonts/6x10.bdf"; // Relative path to a BDF font file
                                          // Assumes you run from matrix_cpp_simple dir
                                          // and rpi-rgb-led-matrix is in the parent dir (~)

// --- Global variable for signal handling ---
// This flag is set to true when Ctrl+C (SIGINT) or SIGTERM is received.
volatile bool interrupt_received = false;
// --- REPLACE WITH YOUR INFLUXDB v1.x DETAILS ---
const std::string INFLUXDB_URL = "http://192.168.0.230:8086"; // e.g., "http://192.168.1.50:8086"
const std::string INFLUXDB_DATABASE = "heat"; // e.g., "telegraf" or "pi_sensors_db"
const std::string INFLUXDB_USER = ""; // Optional: "your_influx_username" - leave empty if no auth
const std::string INFLUXDB_PASSWORD = ""; // Optional: "your_influx_password" - leave empty if no auth


const std::string INFLUXQL_QUERY = "SELECT \"value\" FROM \"esp/sypialnia\" ORDER BY time DESC LIMIT 5";


size_t WriteCallback(void *contents, size_t size, size_t nmemb, void *userp) {
    ((std::string*)userp)->append((char*)contents, size * nmemb);
    return size * nmemb; // Tell curl how many bytes we handled
}


static void InterruptHandler(int signo) {
    interrupt_received = true; // Set the flag
  }


std::string url_encode(const std::string &value) {
    CURL *curl = curl_easy_init();
    std::string result = "";
    if(curl) {
        char *output = curl_easy_escape(curl, value.c_str(), value.length());
        if(output) {
            result = output;
            curl_free(output);
        }
    }
    curl_easy_cleanup(curl); // Clean up the temporary handle
    return result;
}


int main() {
    CURL *curl;
    CURLcode res;
    std::string readBuffer; // String to store the response from InfluxDB
    long http_code = 0;


  rgb_matrix::RGBMatrix::Options matrix_options;
  rgb_matrix::RuntimeOptions runtime_options;

  matrix_options.rows = MATRIX_ROWS;
  matrix_options.cols = MATRIX_COLS;
  matrix_options.chain_length = MATRIX_CHAIN;
  matrix_options.parallel = MATRIX_PARALLEL;
   matrix_options.limit_refresh_rate_hz = 75;
  // Set other common options
  matrix_options.brightness = MATRIX_BRIGHTNESS;
  matrix_options.hardware_mapping = HARDWARE_MAPPING;
  // matrix_options.pwm_lsb_nanoseconds = 130; // Example: uncomment to override default timing
   matrix_options.show_refresh_rate = true; // Example: uncomment to show refresh rate
  matrix_options.hardware_mapping = HARDWARE_MAPPING;
  // Configure runtime options
  // IMPORTANT: If running with sudo (required for hardware access), setting this
  // to true might cause issues trying to drop privileges unnecessarily.
  runtime_options.drop_privileges = false;

  rgb_matrix::RGBMatrix *matrix = rgb_matrix::RGBMatrix::CreateFromOptions(matrix_options, runtime_options);
  if (matrix == nullptr) {
    // Print error and exit if matrix creation fails.
    std::cerr << "Error: Failed to create matrix object. Did you run with sudo? Correct hardware_mapping?" << std::endl;
    return 1; // Indicate failure
  }
  // Success message
  std::cout << "Matrix object created." << std::endl;
  rgb_matrix::FrameCanvas *offscreen_canvas = matrix->CreateFrameCanvas();
  rgb_matrix::Font font;
  if (!font.LoadFont(FONT_PATH)) {
    // Print error and clean up if font loading fails.
    std::cerr << "Error: Couldn't load font '" << FONT_PATH << "'" << std::endl;
    delete matrix; // Clean up matrix object before exiting
    return 1; // Indicate failure
  }
  // Success message
  std::cout << "Font loaded." << std::endl;
  // Define colors using RGB values (0-255)
  rgb_matrix::Color text_color(0, 0, 0); // Green
  rgb_matrix::Color bg_color(255, 255, 255);     // Black

  // Define text position (X, Y coordinate of the baseline)
  int x_pos = 2;                           // Starting X pixel
  // Y position should account for font baseline/height. Add baseline value.
  int y_pos = font.baseline() + 2;         // Position text near top, adjust '2' as needed


  // --- 6. Setup Signal Handler ---
  // Tell the OS to call InterruptHandler function if SIGTERM or SIGINT (Ctrl+C) occurs.
  signal(SIGTERM, InterruptHandler);
  signal(SIGINT, InterruptHandler);

offscreen_canvas->Fill(bg_color.r, bg_color.g, bg_color.b);

rgb_matrix::DrawText(offscreen_canvas, font, x_pos, y_pos, text_color, nullptr, "Hello C++!", 0);


offscreen_canvas = matrix->SwapOnVSync(offscreen_canvas);
std::cout << "Text drawn. Displaying until Ctrl+C is pressed..." << std::endl;



    curl_global_init(CURL_GLOBAL_ALL);
    curl = curl_easy_init();

    if(curl) {
        // 1. Construct the Query URL
        std::string query_params = "db=" + url_encode(INFLUXDB_DATABASE) + "&q=" + url_encode(INFLUXQL_QUERY);

        // Add authentication parameters if username is provided
        if (!INFLUXDB_USER.empty()) {
            query_params += "&u=" + url_encode(INFLUXDB_USER);
            query_params += "&p=" + url_encode(INFLUXDB_PASSWORD);
        }

        std::string full_url = INFLUXDB_URL + "/query?" + query_params;
        std::cout << "Query URL: " << full_url << std::endl; // Print URL for debugging (remove password in real apps)
        curl_easy_setopt(curl, CURLOPT_URL, full_url.c_str());
        curl_easy_setopt(curl, CURLOPT_HTTPGET, 1L); // Use GET request
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteCallback);
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, &readBuffer);
        curl_easy_setopt(curl, CURLOPT_TIMEOUT, 15L); // 15 seconds timeout


        res = curl_easy_perform(curl);

        // 4. Check for errors
        if(res != CURLE_OK) {
            std::cerr << "curl_easy_perform() failed: " << curl_easy_strerror(res) << std::endl;
        } else {

            curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_code);
            std::cout << "HTTP Response Code: " << http_code << std::endl;

            if (http_code == 200) {
                std::cout << "\n--- InfluxDB Response ---" << std::endl;
                std::cout << readBuffer << std::endl;
                std::cout << "-------------------------" << std::endl;


                    json jsonData = json::parse(readBuffer);
                    std::string value_random;
                   value_random = jsonData["results"][0]["series"][0]["values"][0][0];
                  std::cout << value_random << std::endl;

            } else {
                std::cerr << "InfluxDB query failed. HTTP Status: " << http_code << std::endl;
                std::cerr << "Response Body:\n" << readBuffer << std::endl; // Print error response from InfluxDB
            }
        }

        // 5. Cleanup
        curl_easy_cleanup(curl);
    } else {
        std::cerr << "Error: Failed to initialize curl handle." << std::endl;
    }

    curl_global_cleanup();
    const int buffer_size = 100;
    char time_str[buffer_size];
    while (true) { 
        std::time_t now = std::time(nullptr);
        std::tm* local_time = std::localtime(&now);
        std::cout << std::put_time(local_time, "%H:%M:%S") << std::endl;
        std::strftime(time_str, buffer_size, "%H:%M:%S", local_time);
    offscreen_canvas->Fill(bg_color.r, bg_color.g, bg_color.b);
   // std::cout << value_random_1 << std::endl;

    rgb_matrix::DrawText(offscreen_canvas, font, x_pos, y_pos, text_color, nullptr, time_str, 0);
    
    
    offscreen_canvas = matrix->SwapOnVSync(offscreen_canvas);    
    usleep(5000000);
    }
  // --- 10. Cleanup ---
  std::cout << "Cleaning up..." << std::endl;
  // Clear the matrix display (turn off all LEDs).
  matrix->Clear();
  // Delete the matrix object. This also cleans up the associated canvas.
  delete matrix;

  std::cout << "Exiting." << std::endl;    

    return 0;
}
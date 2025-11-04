// Targeted Hardware: Espressif ESP32-S3-DevKitC-1-N8R8
// This code uses FreeRTOS tasks for concurrent operation:
// Core 0: CAN Logging (low latency)
// Core 1: Button Monitoring, Web Server (Config), or GSM/MQTT (Operational)
//
// Libraries assumed to be installed (standard): 
// <SD.h>, <RTClib.h>, <Preferences.h>, <WiFi.h>, <WebServer.h>, <PubSubClient.h>

#include <SPI.h>
#include <SD.h>
#include <PubSubClient.h> 
#include <Arduino.h> 
#include <time.h> 
#include <Wire.h> 
#include <RTClib.h> 
#include <Preferences.h> 
#include <WiFi.h>        
#include <WebServer.h>   

// =================================================================
// 1. HARDWARE DEFINITIONS AND CONFIGURATION
// =================================================================
// NOTE: Verify these GPIO pins are used for external modules (CAN/SD) 
// and do not conflict with built-in flash/PSRAM pins on the S3 module.
#define SD_CS 5     
#define CAN_CS_1 10   // Engine CAN (CAN Bus 1)
#define CAN_CS_2 9    // TTC CAN (CAN Bus 2)

// --- Configuration Button (GPIO 0 is the BOOT button on S3 DevKitC-1) ---
#define CONFIG_BUTTON_PIN 0 
#define CONFIG_HOLD_TIME_MS 3000 // 3 seconds to activate config mode

// --- CLOUD & LOG CONFIGURATION ---
const char* MQTT_SERVER = "your.mqtt.broker.com";
const int MQTT_PORT = 1883; 

// Mock Network Client for MQTT (Global declaration for scope)
Client gsmClient; 
PubSubClient mqttClient(gsmClient); 

// =================================================================
// 2. CONFIGURATION & WEB SERVER DEFINITIONS
// =================================================================

// Web Portal AP Credentials
const char* AP_SSID = "CAN_LOGGER_CONFIG";
const char* AP_PASS = "1234567890"; 

// Configuration Storage Keys
const char* PREFS_NAMESPACE = "can_config";
const char* PREFS_KEY_NAME = "machine_name";
const char* PREFS_KEY_VIN = "vin_number";
const char* PREFS_KEY_PASS = "admin_pass";
// Updated keys for clarity
const char* PREFS_KEY_ENGINE_BAUD = "eng_can_baud"; 
const char* PREFS_KEY_TTC_BAUD = "ttc_can_baud"; 

// Default Configuration Values
const char* DEFAULT_MACHINE_NAME = "Unnamed Machine";
const char* DEFAULT_MACHINE_TYPE = "Tractor"; // Added for completeness in UI
const char* DEFAULT_VIN = "VIN_UNKNOWN";
const char* DEFAULT_ADMIN_PASS = "admin123"; 
const uint32_t DEFAULT_ENGINE_BAUDRATE = 500000; // Default Engine CAN: J1939 standard 500kbps
const uint32_t DEFAULT_TTC_BAUDRATE = 250000;    // Default TTC CAN: Common lower speed 250kbps

// --- Configuration Structure (Stored in Preferences/EEPROM) ---
struct MachineConfig {
    char machineName[32];
    char machineType[32];
    char vinNumber[64];
    char adminPassword[32]; 
    uint32_t engineCanBaudRate; // Baud Rate for Engine CAN
    uint32_t ttcCanBaudRate;    // Baud Rate for TTC CAN
};

MachineConfig currentConfig;
WebServer server(80);
Preferences preferences;
volatile bool isLoggedIn = false; 

// --- System State and Task Handles ---
enum DeviceMode {
    BOOT_CHECK = 0,
    OPERATIONAL_MODE, // GSM/CAN Logging
    CONFIG_MODE       // WiFi AP/Web Server
};

volatile DeviceMode currentMode = BOOT_CHECK;
TaskHandle_t configPortalTaskHandle = NULL; 
TaskHandle_t mqttSenderTaskHandle = NULL;

// Global State (Simplified)
volatile uint16_t engineSpeedRpm = 0; 
bool isTimeSet = false; 
unsigned long lastMqttSendTime = 0; 
RTC_DS1307 rtc; 

// SD/CAN State (Simplified)
struct CanLoggerState {
    uint8_t csPin;
    String busName; 
    uint32_t *baudRatePtr; // Pointer to the correct baud rate in currentConfig
    bool sdInitialized = false; 
};

// Initialize canState1 to point to engineCanBaudRate
CanLoggerState engineCanState = { CAN_CS_1, "ENGINE_CAN", &currentConfig.engineCanBaudRate };
// Initialize canState2 to point to ttcCanBaudRate
CanLoggerState ttcCanState = { CAN_CS_2, "TTC_CAN", &currentConfig.ttcCanBaudRate };


// =================================================================
// 3. CONFIGURATION MANAGEMENT
// =================================================================

void loadConfiguration() {
    preferences.begin(PREFS_NAMESPACE, true); 
    preferences.getString(PREFS_KEY_NAME, DEFAULT_MACHINE_NAME, currentConfig.machineName, sizeof(currentConfig.machineName));
    preferences.getString("machine_type", DEFAULT_MACHINE_TYPE, currentConfig.machineType, sizeof(currentConfig.machineType));
    preferences.getString(PREFS_KEY_VIN, DEFAULT_VIN, currentConfig.vinNumber, sizeof(currentConfig.vinNumber));
    preferences.getString(PREFS_KEY_PASS, DEFAULT_ADMIN_PASS, currentConfig.adminPassword, sizeof(currentConfig.adminPassword));
    // Load both CAN Baud Rates
    currentConfig.engineCanBaudRate = preferences.getUInt(PREFS_KEY_ENGINE_BAUD, DEFAULT_ENGINE_BAUDRATE); 
    currentConfig.ttcCanBaudRate = preferences.getUInt(PREFS_KEY_TTC_BAUD, DEFAULT_TTC_BAUDRATE); 
    preferences.end();
    
    Serial.println("Configuration Loaded.");
    Serial.printf("-> Engine CAN Baud Rate: %u\n", currentConfig.engineCanBaudRate);
    Serial.printf("-> TTC CAN Baud Rate: %u\n", currentConfig.ttcCanBaudRate);
}

void saveConfiguration() {
    preferences.begin(PREFS_NAMESPACE, false); 
    preferences.putString(PREFS_KEY_NAME, currentConfig.machineName);
    preferences.putString("machine_type", currentConfig.machineType);
    preferences.putString(PREFS_KEY_VIN, currentConfig.vinNumber);
    preferences.putString(PREFS_KEY_PASS, currentConfig.adminPassword);
    // Save both CAN Baud Rates
    preferences.putUInt(PREFS_KEY_ENGINE_BAUD, currentConfig.engineCanBaudRate); 
    preferences.putUInt(PREFS_KEY_TTC_BAUD, currentConfig.ttcCanBaudRate); 
    preferences.end();
    Serial.println("Configuration Saved.");
}

// =================================================================
// 4. MODE SWITCHING FUNCTIONS
// =================================================================

/**
 * @brief Starts the GSM/MQTT tasks for cloud communication and data transfer.
 */
void enter_operational_mode() {
    // 1. Turn off Wi-Fi if it was active
    WiFi.mode(WIFI_OFF);
    Serial.println("WiFi OFF. Starting Operational (GSM/CAN) Mode.");
    
    // 2. Start GSM/MQTT tasks on Core 1
    if (mqttSenderTaskHandle == NULL) {
        xTaskCreatePinnedToCore(mqtt_sender_task, "MQTTSend", 10000, NULL, 1, &mqttSenderTaskHandle, 1);
        Serial.println("MQTTSend Task Started.");
    }
    
    currentMode = OPERATIONAL_MODE;
}

/**
 * @brief Sets up the Wi-Fi AP and starts the Web Server for configuration.
 */
void enter_config_mode() {
    Serial.println("Entering Configuration Mode via Button Hold.");
    currentMode = CONFIG_MODE;
    
    // 1. Start the configuration portal task on Core 1
    if (configPortalTaskHandle == NULL) {
        xTaskCreatePinnedToCore(config_portal_task, "ConfigPortal", 10000, NULL, 1, &configPortalTaskHandle, 1);
        Serial.println("ConfigPortal Task Started.");
    }
}


// =================================================================
// 5. WEB SERVER HANDLERS & UI
// =================================================================

// Helper function to generate the main HTML page
String getConfigurationPageHtml(bool success = false, bool isSave = false, String message = "") {
    String html = R"raw(<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Logger Config</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>.container { max-width: 500px; }</style>
</head>
<body class="bg-gray-100 p-4 font-sans">
<div class="container mx-auto p-6 bg-white rounded-xl shadow-2xl border-t-4 border-indigo-500">
    <h1 class="text-3xl font-extrabold text-center mb-6 text-indigo-700">ESP32-S3 Datalogger Config</h1>
)raw";

    if (isLoggedIn) {
        html += "<div class='mb-6'>";
        if (isSave) {
            html += "<p class='text-center text-sm font-semibold p-3 rounded-lg ";
            html += success ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700";
            html += "'>" + message + "</p>";
        }
        
        // --- Configuration Form ---
        html += R"raw(<form action="/save" method="post" class="mt-4 space-y-4">
            <div class="config-section p-4 bg-indigo-50 rounded-lg">
                <h2 class="text-xl font-bold mb-4 text-indigo-800">Machine Details</h2>
                <div>
                    <label for="name" class="block text-sm font-medium text-gray-700">Machine Name</label>
                    <input type="text" id="name" name="machineName" required maxlength="31"
                           value=")raw";
        html += String(currentConfig.machineName);
        html += R"raw(" class="mt-1 block w-full rounded-md border-gray-300 shadow-sm p-3 border focus:ring-indigo-500 focus:border-indigo-500 transition duration-150">
                </div>
                <div>
                    <label for="type" class="block text-sm font-medium text-gray-700">Machine Type</label>
                    <input type="text" id="type" name="machineType" required maxlength="31"
                           value=")raw";
        html += String(currentConfig.machineType);
        html += R"raw(" class="mt-1 block w-full rounded-md border-gray-300 shadow-sm p-3 border focus:ring-indigo-500 focus:border-indigo-500 transition duration-150">
                </div>
                <div>
                    <label for="vin" class="block text-sm font-medium text-gray-700">VIN Number</label>
                    <input type="text" id="vin" name="vinNumber" required maxlength="63"
                           value=")raw";
        html += String(currentConfig.vinNumber);
        html += R"raw(" class="mt-1 block w-full rounded-md border-gray-300 shadow-sm p-3 border focus:ring-indigo-500 focus:border-indigo-500 transition duration-150">
                </div>
            </div>
            
            <div class="config-section p-4 bg-red-50 rounded-lg">
                <h2 class="text-xl font-bold mb-4 text-red-800">Dual CAN Bus Setup</h2>
                
                <!-- Engine CAN Baud Rate Field -->
                <div class="mb-3">
                    <label for="baud1" class="block text-sm font-medium text-gray-700">Engine CAN Baud Rate (CS: 10)</label>
                    <input type="number" id="baud1" name="engineCanBaudRate" required min="10000" max="1000000"
                           value=")raw";
        html += String(currentConfig.engineCanBaudRate);
        html += R"raw(" class="mt-1 block w-full rounded-md border-gray-300 shadow-sm p-3 border focus:ring-red-500 focus:border-red-500 transition duration-150">
                    <p class="text-xs text-gray-500 mt-1">Typical: 500000 (J1939) or 250000.</p>
                </div>

                <!-- TTC CAN Baud Rate Field -->
                <div>
                    <label for="baud2" class="block text-sm font-medium text-gray-700">TTC CAN Baud Rate (CS: 9)</label>
                    <input type="number" id="baud2" name="ttcCanBaudRate" required min="10000" max="1000000"
                           value=")raw";
        html += String(currentConfig.ttcCanBaudRate);
        html += R"raw(" class="mt-1 block w-full rounded-md border-gray-300 shadow-sm p-3 border focus:ring-red-500 focus:border-red-500 transition duration-150">
                    <p class="text-xs text-gray-500 mt-1">Typical: 125000 or 250000.</p>
                </div>
            </div>
            
            <div class="config-section p-4 bg-yellow-50 rounded-lg">
                <h2 class="text-xl font-bold mb-4 text-yellow-800">Security</h2>
                <div>
                    <label for="password" class="block text-sm font-medium text-gray-700">Admin Password (New)</label>
                    <input type="password" id="password" name="adminPassword" placeholder="Keep blank to retain current password" maxlength="31"
                           class="mt-1 block w-full rounded-md border-gray-300 shadow-sm p-3 border focus:ring-yellow-500 focus:border-yellow-500 transition duration-150">
                </div>
            </div>
            
            <button type="submit" class="w-full py-3 px-4 border border-transparent rounded-lg shadow-lg text-lg font-bold text-white bg-green-600 hover:bg-green-700 transition duration-200 transform hover:scale-[1.01] focus:outline-none focus:ring-4 focus:ring-offset-2 focus:ring-green-500">
                Save Config & Switch to Operational (GSM) Mode
            </button>
        </form>)raw";
        
        // --- SD Card Link ---
        html += R"raw(
        <div class="mt-6 pt-4 border-t border-gray-200">
            <h2 class="text-xl font-bold mb-4 text-gray-800">Data Management</h2>
            <a href="/files" class="w-full block text-center py-3 px-4 border border-indigo-600 rounded-lg shadow-md text-base font-bold text-indigo-600 bg-white hover:bg-indigo-50 transition duration-200">
                View & Download SD Card Files
            </a>
        </div>
        )raw";

    } else {
        // --- Login Form ---
        html += R"raw(<form action="/login" method="post" class="space-y-6 p-4 bg-gray-50 rounded-lg shadow-inner">
            <h2 class="text-2xl font-bold mb-4 text-gray-800 border-b pb-2">Login Required</h2>
            <div>
                <label for="pass" class="block text-base font-medium text-gray-700">Password</label>
                <input type="password" id="pass" name="password" required
                       class="mt-1 block w-full rounded-md border-gray-300 shadow-md p-3 border focus:ring-indigo-500 focus:border-indigo-500">
            </div>
            <button type="submit" class="w-full py-3 px-4 border border-transparent rounded-lg shadow-lg text-lg font-bold text-white bg-indigo-600 hover:bg-indigo-700 transition duration-200">
                Secure Login
            </button>
            <p class="text-center text-sm text-gray-500 mt-4">Connect to AP: **)raw";
        html += AP_SSID;
        html += R"raw(** | Current IP: )raw";
        html += WiFi.softAPIP().toString();
        html += R"raw(</p>
        </form>)raw";
    }

    html += "</div></body></html>";
    return html;
}

void handleRoot() {
    server.send(200, "text/html", getConfigurationPageHtml());
}

void handleLogin() {
    if (server.hasArg("password") && server.arg("password") == String(currentConfig.adminPassword)) {
        isLoggedIn = true;
        server.sendHeader("Location", "/", true); 
        server.send(302, "text/plain", "Logged In");
    } else {
        // Error message using inline style (No alerts)
        String html = "<h1 style='color: red; text-align: center; margin-top: 50px;'>Unauthorized</h1>";
        html += "<p style='text-align: center;'>Incorrect password. <a href='/' style='color: blue;'>Try again</a>.</p>";
        server.send(401, "text/html", html);
    }
}

// Helper to safely update a baud rate value
void updateBaudRate(const char* argName, uint32_t& targetBaudRate) {
    if (server.hasArg(argName)) {
        uint32_t newBaud = server.arg(argName).toInt();
        // Sanity check: between 10k and 1M bps is usually safe for CAN
        if (newBaud >= 10000 && newBaud <= 1000000) { 
            targetBaudRate = newBaud;
        } else {
            Serial.printf("Invalid baud rate received for %s: %s. Retaining old value: %u\n", 
                          argName, server.arg(argName).c_str(), targetBaudRate);
        }
    }
}

void handleSave() {
    if (!isLoggedIn) {
        server.sendHeader("Location", "/", true);
        server.send(302, "text/plain", "Redirecting to login");
        return;
    }
    
    // Update config: Machine details
    if (server.hasArg("machineName")) {
        strncpy(currentConfig.machineName, server.arg("machineName").c_str(), sizeof(currentConfig.machineName) - 1);
        currentConfig.machineName[sizeof(currentConfig.machineName) - 1] = '\0';
    }
    if (server.hasArg("machineType")) {
        strncpy(currentConfig.machineType, server.arg("machineType").c_str(), sizeof(currentConfig.machineType) - 1);
        currentConfig.machineType[sizeof(currentConfig.machineType) - 1] = '\0';
    }
    if (server.hasArg("vinNumber")) {
        strncpy(currentConfig.vinNumber, server.arg("vinNumber").c_str(), sizeof(currentConfig.vinNumber) - 1);
        currentConfig.vinNumber[sizeof(currentConfig.vinNumber) - 1] = '\0';
    }
    
    // Check for password change
    if (server.hasArg("adminPassword") && server.arg("adminPassword").length() > 0) {
        strncpy(currentConfig.adminPassword, server.arg("adminPassword").c_str(), sizeof(currentConfig.adminPassword) - 1);
        currentConfig.adminPassword[sizeof(currentConfig.adminPassword) - 1] = '\0';
    }

    // NEW: Handle CAN Baud Rates for both buses, using new names
    updateBaudRate("engineCanBaudRate", currentConfig.engineCanBaudRate);
    updateBaudRate("ttcCanBaudRate", currentConfig.ttcCanBaudRate);

    saveConfiguration();
    
    // 1. Send success message to the client before shutting down
    String finalMsg = "Configuration saved successfully! (Engine CAN: ";
    finalMsg += String(currentConfig.engineCanBaudRate);
    finalMsg += ", TTC CAN: ";
    finalMsg += String(currentConfig.ttcCanBaudRate);
    finalMsg += ") Device is now shutting down Wi-Fi AP and switching to **GSM/Cloud Operational Mode**. You may now disconnect from the '";
    finalMsg += AP_SSID;
    finalMsg += "' Wi-Fi network.";
    server.send(200, "text/html", getConfigurationPageHtml(true, true, finalMsg));
    
    // 2. Short delay to allow the response to be sent fully
    delay(100); 

    // 3. Stop the WebServer and AP
    server.stop();
    WiFi.softAPdisconnect(true);
    
    // 4. Stop the current portal task
    if (configPortalTaskHandle != NULL) {
        vTaskDelete(configPortalTaskHandle);
        configPortalTaskHandle = NULL;
    }
    
    // 5. Switch to Operational Mode (GSM/CAN Logging)
    enter_operational_mode();
}

void handleFiles() {
    if (!isLoggedIn) {
        server.sendHeader("Location", "/", true);
        server.send(302, "text/plain", "Redirecting to login");
        return;
    }
    
    String html = R"raw(<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>SD Card Files</title><script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-gray-100 p-4 font-sans">
<div class="container mx-auto p-6 bg-white rounded-xl shadow-2xl border-t-4 border-indigo-500">
    <h1 class="text-2xl font-bold mb-6 text-indigo-700">SD Card File Browser</h1>
    <a href="/" class="mb-4 inline-flex items-center text-indigo-600 hover:text-indigo-800 transition duration-150">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 mr-1" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M9.707 16.707a1 1 0 01-1.414 0l-6-6a1 1 0 010-1.414l6-6a1 1 0 011.414 1.414L5.414 9H17a1 1 0 110 2H5.414l4.293 4.293a1 1 0 010 1.414z" clip-rule="evenodd" /></svg>
        Back to Configuration
    </a>
    <div class="mt-4 space-y-2">)raw";
    
    // --- MOCK SD CARD LISTING (SD library needs proper SPI setup to list real files) ---
    html += "<p class='text-sm font-bold text-red-600'>[NOTICE] SD card functionality is MOCKED. Please ensure proper SPI library is included if using an external SD card reader.</p>";
    
    String mock_files[] = {"LOG_20251104.csv", "LOG_20251103.csv", "LOG_20251102.csv", "CONFIG.BIN"};
    for (int i = 0; i < 4; i++) {
        String path = mock_files[i];
        html += "<div class='flex justify-between items-center p-3 bg-gray-50 rounded-lg shadow-sm'>";
        html += "<span>" + path + " (8.2 KB)</span>";
        html += "<a href='/download?file=" + path + "' class='text-sm font-medium text-white bg-green-500 hover:bg-green-600 px-3 py-1 rounded-md transition duration-150'>Download</a>";
        html += "</div>";
    }
    
    html += "</div></div></body></html>";
    server.send(200, "text/html", html);
}

void handleDownload() {
    if (!isLoggedIn) {
        server.sendHeader("Location", "/", true);
        server.send(302, "text/plain", "Redirecting to login");
        return;
    }
    
    if (!server.hasArg("file")) {
        server.send(400, "text/plain", "File parameter missing");
        return;
    }
    String path = server.arg("file");

    // MOCK Download: Generate a mock CSV response with current config data
    String content = "Timestamp,VIN,MachineName,Engine_Baud,TTC_Baud,RPM_Mock,Status\n";
    content += "2025-11-04T12:00:00Z," + String(currentConfig.vinNumber) + "," + String(currentConfig.machineName) + ",";
    content += String(currentConfig.engineCanBaudRate) + "," + String(currentConfig.ttcCanBaudRate) + ",1500,OK\n";
    content += "2025-11-04T12:00:05Z," + String(currentConfig.vinNumber) + "," + String(currentConfig.machineName) + ",";
    content += String(currentConfig.engineCanBaudRate) + "," + String(currentConfig.ttcCanBaudRate) + ",1550,OK\n";

    Serial.printf("MOCK Downloading file: %s\n", path.c_str());
    
    server.sendHeader("Content-Disposition", "attachment; filename=" + path);
    server.setContentLength(content.length());
    server.send(200, "text/csv", content);
}


void setup_web_server() {
    WiFi.softAP(AP_SSID, AP_PASS);
    IPAddress apIP = WiFi.softAPIP();
    Serial.printf("Access Point Started. Connect to: %s\n", AP_SSID);
    Serial.printf("Web Server IP: %s\n", apIP.toString().c_str());
    
    server.on("/", HTTP_GET, handleRoot);
    server.on("/login", HTTP_POST, handleLogin);
    server.on("/save", HTTP_POST, handleSave);
    server.on("/files", HTTP_GET, handleFiles);
    server.on("/download", HTTP_GET, handleDownload);

    server.begin();
}


// =================================================================
// 6. FREERTOS TASK DEFINITIONS
// =================================================================

// --- Task 1: Button Monitor Task (Core 1) ---
void button_monitor_task(void *pvParameters) {
    // Set up GPIO 0 as input with pull-up
    pinMode(CONFIG_BUTTON_PIN, INPUT_PULLUP); 
    unsigned long pressStartTime = 0;
    bool isPressed = false;
    
    // Give time for power stabilization and initial Serial print
    vTaskDelay(pdMS_TO_TICKS(1000)); 

    Serial.println("Monitoring Config Button (GPIO 0)...");
    
    while (currentMode == BOOT_CHECK) {
        if (digitalRead(CONFIG_BUTTON_PIN) == LOW) {
            if (!isPressed) {
                isPressed = true;
                pressStartTime = millis();
                Serial.println("Button Pressed.");
            } else if (millis() - pressStartTime >= CONFIG_HOLD_TIME_MS) {
                // Button held for > 3 seconds -> Enter Config Mode
                Serial.println("!!! CONFIG MODE ACTIVATED (3s hold) !!!");
                enter_config_mode();
                vTaskDelete(NULL); // Delete this task
                return;
            }
        } else {
            if (isPressed) {
                // Button released before 3 seconds -> Enter Operational Mode
                Serial.println("Button released quickly. Entering default Operational Mode (GSM/CAN).");
                enter_operational_mode();
                vTaskDelete(NULL); // Delete this task
                return;
            }
            isPressed = false;
        }

        vTaskDelay(pdMS_TO_TICKS(50)); // Debounce/check frequency
    }
}

// --- Task 2: Configuration Portal Task (Core 1) ---
void config_portal_task(void *pvParameters) {
    setup_web_server();
    
    while (currentMode == CONFIG_MODE) {
        server.handleClient(); 
        vTaskDelay(pdMS_TO_TICKS(10)); 
    }
}


// --- Task 3: MQTT Sender/GSM Cloud Task (Core 1) ---
void mqtt_sender_task(void *pvParameters) {
    Serial.println("MOCK GSM/MQTT: Initializing connection...");
    
    while (currentMode == OPERATIONAL_MODE) {
        if (millis() - lastMqttSendTime >= 10000) { // Check and upload every 10s
            // MOCK GSM Network Check & MQTT Connect
            Serial.println("MOCK GSM/MQTT: Uploading data...");

            // 1. MOCK Telemetry Upload (Using latest configuration)
            String msg = "{\"machine_name\":\"" + String(currentConfig.machineName) + "\"";
            msg += ",\"vin\":\"" + String(currentConfig.vinNumber) + "\"";
            msg += ",\"engine_can_baud\":" + String(currentConfig.engineCanBaudRate); // Include Engine Baud Rate
            msg += ",\"ttc_can_baud\":" + String(currentConfig.ttcCanBaudRate);      // Include TTC Baud Rate
            msg += ",\"speed_rpm\":" + String(engineSpeedRpm);        
            msg += ",\"status\":\"Operational\"";
            msg += "}";
            
            Serial.printf("MOCK MQTT Telemetry Sent: %s\n", msg.c_str());
            
            // 2. MOCK Log File Transfer (SD Card to Cloud)
            Serial.println("MOCK GSM/CLOUD: Transferring log files from SD card...");
            
            lastMqttSendTime = millis();
        }
        
        vTaskDelay(pdMS_TO_TICKS(1000)); 
    }
    vTaskDelete(NULL);
}


// --- Task 4: CAN Logger Task (Core 0) ---
void can_logger_task(void *pvParameters) {
    CanLoggerState* state = (CanLoggerState*)pvParameters;
    
    // Dereference the pointer to get the current baud rate value
    uint32_t currentBaud = *(state->baudRatePtr);
    
    Serial.printf("CAN Logger %s starting on Core 0 with Baud: %u...\n", state->busName.c_str(), currentBaud);
    
    // NOTE: This is where you would call your CAN initialization function:
    // CAN_Controller_Init(state->csPin, currentBaud);
    
    // MOCK: SD Card Initialization (Runs once)
    static bool sd_init_mocked = false;
    if (!sd_init_mocked) {
        Serial.println("MOCK: SD Card initialized successfully.");
        state->sdInitialized = true;
        sd_init_mocked = true;
    }

    while (1) {
        // MOCK: CAN Read (Simulate engine speed update quickly)
        static unsigned long last_mock_can = 0;
        if (millis() - last_mock_can > 50) {
            engineSpeedRpm = random(800, 2200);
            last_mock_can = millis();
        }
        
        // Data logging to SD card runs continuously regardless of network mode
        if (state->sdInitialized) {
            // MOCK: Log data to SD card file here...
        }

        vTaskDelay(pdMS_TO_TICKS(1)); // Run frequently for low-latency CAN bus monitoring
    }
}

// =================================================================
// 7. UTILITY AND SETUP
// =================================================================

bool sync_time_from_rtc() {
    // MOCK/Placeholder for RTC
    Wire.begin();
    if (!rtc.begin()) {
        Serial.println("RTC ERROR: Couldn't find RTC. Using default boot time.");
        isTimeSet = false;
        return false;
    }
    // Set time/sync time functions omitted for brevity
    isTimeSet = true;
    Serial.println("RTC: Time synchronized.");
    return true;
}

void setup() {
    Serial.begin(115200);
    delay(1000);

    // 1. Initialize RTC and Load Persistent Configuration
    sync_time_from_rtc(); 
    loadConfiguration();

    // 2. Start CAN Logger Tasks (Core 0: Runs continuously to read data)
    // CAN state objects are passed to their respective tasks.
    xTaskCreatePinnedToCore(can_logger_task,"CAN_ENG",10000, &engineCanState, 2, NULL, 0);
    xTaskCreatePinnedToCore(can_logger_task,"CAN_TTC",10000, &ttcCanState, 2, NULL, 0);
    
    // 3. Start the Button Monitor Task (Core 1: Determines initial mode)
    // The device waits here until the button is released/held.
    xTaskCreatePinnedToCore(button_monitor_task, "ButtonMonitor", 3000, NULL, 3, NULL, 1);
    
    // The program flow is now handled by the FreeRTOS tasks.
    lastMqttSendTime = millis();
}

void loop() {
    // The Arduino loop should remain empty when using FreeRTOS for all control
    vTaskDelay(pdMS_TO_TICKS(1000));
}

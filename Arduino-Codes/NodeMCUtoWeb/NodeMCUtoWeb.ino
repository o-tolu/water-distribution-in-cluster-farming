#include <Wire.h>
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <ArduinoJson.h>
#include "secrets.h"

// WiFi & Server Configuration (defined in local secrets.h; see secrets.example.h)
const char* ssid = WIFI_SSID;
const char* password = WIFI_PASSWORD;
const char* serverUrl = SERVER_URL;
const char* endpoint = "/api/flow-data/";

// Flow meter variables
float flowRate1 = 0.0, volume1 = 0.0;
float flowRate2 = 0.0, volume2 = 0.0;
float flowRate3 = 0.0, volume3 = 0.0;

void setup() {
  // Initialize Serial Communication
  Serial.begin(9600);
  Serial.println("\nInitializing...");

  // Connect to WiFi
  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi Connected!");
  Serial.println("IP Address: " + WiFi.localIP().toString());

  // Initialize I2C Communication
  Wire.begin(4, 5); // NodeMCU I2C: GPIO 4 (SDA), GPIO 5 (SCL)
  Serial.println("I2C Communication Initialized");
}

void sendSensorData(int sensorId, float flowRate, float volume) {
    if (WiFi.status() == WL_CONNECTED) {
        WiFiClient client;
        HTTPClient http;

        String url = String(serverUrl) + ":8000" + endpoint;
        
        if (http.begin(client, url)) {
            http.addHeader("Content-Type", "application/x-www-form-urlencoded");
            
            String postData = "sensor_id=" + String(sensorId) + 
                            "&flowRate=" + String(flowRate, 2) + 
                            "&volume=" + String(volume, 2);
            
            Serial.println("\nSending to: " + url);
            Serial.println("Data: " + postData);
            
            int httpCode = http.POST(postData);
            
            if (httpCode > 0) {
                String response = http.getString();
                Serial.printf("[HTTP] POST... code: %d\n", httpCode);
                Serial.println("Response: " + response);
                
                // Only try to parse JSON if request was successful
                if (httpCode == 200 || httpCode == 201) {
                    StaticJsonDocument<400> doc; // Increased buffer size
                    DeserializationError error = deserializeJson(doc, response);
                    
                    if (!error) {
                        // Check if valve_status exists in response
                        if (doc.containsKey("valve_status")) {
                            const char* valveStatus = doc["valve_status"];
                            
                            // Send valve control command to Arduino
                            Wire.beginTransmission(8);
                            Wire.write('V');  // Command identifier
                            Wire.write(sensorId);  // Sensor ID
                            Wire.write(valveStatus[0]);  // 'O' for OPEN or 'C' for CLOSE
                            Wire.endTransmission();
                            
                            Serial.printf("Valve command sent for sensor %d: %s\n", 
                                        sensorId, valveStatus);
                        } else {
                            // Default to CLOSE if no valve status
                            Wire.beginTransmission(8);
                            Wire.write('V');
                            Wire.write(sensorId);
                            Wire.write('C');
                            Wire.endTransmission();
                            Serial.printf("No valve status in response. Closing valve %d\n", sensorId);
                        }
                    } else {
                        Serial.printf("JSON Parse Error: %s\n", error.c_str());
                    }
                } else {
                    // Handle error response - close valve
                    Wire.beginTransmission(8);
                    Wire.write('V');
                    Wire.write(sensorId);
                    Wire.write('C');
                    Wire.endTransmission();
                    Serial.printf("Error response. Closing valve %d\n", sensorId);
                }
            } else {
                Serial.printf("[HTTP] POST... failed, error: %s\n", http.errorToString(httpCode).c_str());
            }
            
            http.end();
        }
    }
}

void loop() {
  // Check WiFi connection
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi Connection Lost! Reconnecting...");
    WiFi.begin(ssid, password);
    delay(5000);
    return;
  }

  // Request data from Arduino
  Wire.requestFrom(8, sizeof(flowRate1) + sizeof(volume1) + 
                     sizeof(flowRate2) + sizeof(volume2) + 
                     sizeof(flowRate3) + sizeof(volume3));

  // Check if correct amount of data is available
  if (Wire.available() == sizeof(flowRate1) + sizeof(volume1) + 
                         sizeof(flowRate2) + sizeof(volume2) + 
                         sizeof(flowRate3) + sizeof(volume3)) {
    
    // Read sensor data
    float newFlowRate1, newVolume1;
    float newFlowRate2, newVolume2;
    float newFlowRate3, newVolume3;

    Wire.readBytes((char*)&newFlowRate1, sizeof(newFlowRate1));
    Wire.readBytes((char*)&newVolume1, sizeof(newVolume1));
    Wire.readBytes((char*)&newFlowRate2, sizeof(newFlowRate2));
    Wire.readBytes((char*)&newVolume2, sizeof(newVolume2));
    Wire.readBytes((char*)&newFlowRate3, sizeof(newFlowRate3));
    Wire.readBytes((char*)&newVolume3, sizeof(newVolume3));

    // Update values (keep volume if no flow)
    if (newFlowRate1 > 0.0) { flowRate1 = newFlowRate1; volume1 = newVolume1; }
    else { flowRate1 = 0.0; }

    if (newFlowRate2 > 0.0) { flowRate2 = newFlowRate2; volume2 = newVolume2; }
    else { flowRate2 = 0.0; }

    if (newFlowRate3 > 0.0) { flowRate3 = newFlowRate3; volume3 = newVolume3; }
    else { flowRate3 = 0.0; }

    // Print readings to Serial
    Serial.println("\n----- Flow Meter Readings -----");
    Serial.printf("Flow 1: %.2f L/min, Volume 1: %.2f L\n", flowRate1, volume1);
    Serial.printf("Flow 2: %.2f L/min, Volume 2: %.2f L\n", flowRate2, volume2);
    Serial.printf("Flow 3: %.2f L/min, Volume 3: %.2f L\n", flowRate3, volume3);
    Serial.println("--------------------------------");

    // Send data for each sensor
    sendSensorData(1, flowRate1, volume1);
    delay(1000); // Small delay between requests
    sendSensorData(2, flowRate2, volume2);
    delay(1000);
    sendSensorData(3, flowRate3, volume3);

  } else {
    Serial.println("Error: Incorrect data size received");
  }

  // Wait before next reading
  delay(1000);
}
#include <Wire.h>
#include <PinChangeInterrupt.h>

volatile int pulseCount1 = 0, pulseCount2 = 0, pulseCount3 = 0;
float volume1 = 0.0, volume2 = 0.0, volume3 = 0.0;
float flowRate1 = 0.0, flowRate2 = 0.0, flowRate3 = 0.0;

const int VALVE_RELAY_1 = 5;  // Change pins as needed
const int VALVE_RELAY_2 = 6;
const int VALVE_RELAY_3 = 7;

unsigned long currentTime;
unsigned long cloopTime;

void pulseCounter1() { pulseCount1++; }
void pulseCounter2() { pulseCount2++; }
void pulseCounter3() { pulseCount3++; }

void setup() {
  Serial.begin(9600);
  Wire.begin(8); // Arduino as I2C Slave
  Wire.onRequest(sendData); // Function to send data when requested

  pinMode(2, INPUT_PULLUP);
  pinMode(3, INPUT_PULLUP);
  pinMode(4, INPUT_PULLUP);

  attachInterrupt(digitalPinToInterrupt(2), pulseCounter1, RISING);
  attachInterrupt(digitalPinToInterrupt(3), pulseCounter2, RISING);
  attachPCINT(digitalPinToPCINT(4), pulseCounter3, RISING);

  Serial.println("Three Water Flow Meters Initialized");


    pinMode(VALVE_RELAY_1, OUTPUT);
    pinMode(VALVE_RELAY_2, OUTPUT);
    pinMode(VALVE_RELAY_3, OUTPUT);
    
    // Initially close all valves
    digitalWrite(VALVE_RELAY_1, HIGH); // Assuming active LOW relays
    digitalWrite(VALVE_RELAY_2, HIGH);
    digitalWrite(VALVE_RELAY_3, HIGH);
    
    Wire.onReceive(receiveValveCommand); // Add handler for valve commands
}

void loop() {
  currentTime = millis();
  if (currentTime >= (cloopTime + 1000)) {
    cloopTime = currentTime;

    bool flowDetected1 = (pulseCount1 != 0);
    bool flowDetected2 = (pulseCount2 != 0);
    bool flowDetected3 = (pulseCount3 != 0);

    // Update flow rates and volumes only if flow is detected
    if (flowDetected1) {
      flowRate1 = (pulseCount1 / 7.5);
      volume1 += (flowRate1 / 60.0);
    } else {
      flowRate1 = 0.0;
    }

    if (flowDetected2) {
      flowRate2 = (pulseCount2 / 7.5);
      volume2 += (flowRate2 / 60.0);
    } else {
      flowRate2 = 0.0;
    }

    if (flowDetected3) {
      flowRate3 = (pulseCount3 / 7.5);
      volume3 += (flowRate3 / 60.0);
    } else {
      flowRate3 = 0.0;
    }

    // Display readings
    Serial.println("--------------------------------------------------");
    Serial.print("Flow Meter 1 - Flow Rate: "); Serial.print(flowRate1); Serial.print(" L/min, Volume: "); Serial.print(volume1); Serial.println(" L");
    Serial.print("Flow Meter 2 - Flow Rate: "); Serial.print(flowRate2); Serial.print(" L/min, Volume: "); Serial.print(volume2); Serial.println(" L");
    Serial.print("Flow Meter 3 - Flow Rate: "); Serial.print(flowRate3); Serial.print(" L/min, Volume: "); Serial.print(volume3); Serial.println(" L");

    // Reset pulse counts for the next interval
    pulseCount1 = 0;
    pulseCount2 = 0;
    pulseCount3 = 0;
  }
}

// Function to send data to NodeMCU
void sendData() {
  Wire.write((byte*)&flowRate1, sizeof(flowRate1));
  Wire.write((byte*)&volume1, sizeof(volume1));
  Wire.write((byte*)&flowRate2, sizeof(flowRate2));
  Wire.write((byte*)&volume2, sizeof(volume2));
  Wire.write((byte*)&flowRate3, sizeof(flowRate3));
  Wire.write((byte*)&volume3, sizeof(volume3));
}


void receiveValveCommand(int byteCount) {
    if (Wire.available() >= 3) {
        char cmd = Wire.read();
        if (cmd == 'V') {  // Valve command
            int sensorId = Wire.read();
            char action = Wire.read();
            
            // Select relay based on sensor ID
            int relayPin;
            switch(sensorId) {
                case 1: relayPin = VALVE_RELAY_1; break;
                case 2: relayPin = VALVE_RELAY_2; break;
                case 3: relayPin = VALVE_RELAY_3; break;
                default: return;
            }
            
            // Control relay based on action
            if (action == 'O') {  // OPEN
                digitalWrite(relayPin, LOW);  // Active LOW relay
                Serial.print("Opening valve ");
                Serial.println(sensorId);
            }
            else if (action == 'C') {  // CLOSE
                digitalWrite(relayPin, HIGH);
                Serial.print("Closing valve ");
                Serial.println(sensorId);
            }
        }
    }
  }


# Development of a Web-Based Administration System for Water Distribution in Cluster Farming

A prepaid IoT water distribution and administration platform for cluster farming, combining flow-rate sensing, automated solenoid valve actuation, and a Django web application with real-time WebSocket monitoring.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Problem Statement & Motivation](#2-problem-statement--motivation)
3. [Project Objectives](#3-project-objectives)
4. [Key Features](#4-key-features)
5. [System Architecture](#5-system-architecture)
6. [Hardware Components](#6-hardware-components)
7. [Software Technologies & Frameworks](#7-software-technologies--frameworks)
8. [How the System Works](#8-how-the-system-works)
9. [Hardware-to-Web Communication](#9-hardware-to-web-communication)
10. [Water Flow Measurement & Token Calculation](#10-water-flow-measurement--token-calculation)
11. [Database & API Overview](#11-database--api-overview)
12. [Installation & Setup Instructions](#12-installation--setup-instructions)
13. [Arduino & NodeMCU Firmware Setup](#13-arduino--nodemcu-firmware-setup)
14. [Configuration Requirements](#14-configuration-requirements)
15. [Screenshots & Documentation](#15-screenshots--documentation)
16. [Contributors](#16-contributors)

---

## 1. Project Overview

**Smart Water Distribution Management (SWDM)** is a web-based administration and prepaid water metering system built for shared irrigation networks in cluster farming. Farmers register on the web portal, are assigned a flow meter (`Sensor 1`, `Sensor 2`, or `Sensor 3`) and a farm cluster location (`Farm A`, `Farm B`, or `Farm C`) by an administrator, purchase prepaid water tokens, and monitor their real-time water flow and remaining volume balance. Solenoid valves automatically open when a farmer has an active token balance and close as soon as the allocated volume is depleted or manually shut off from the dashboard.

## 2. Problem Statement & Motivation

In cluster farming environments where multiple farmers share a centralized water supply, unmanaged distribution leads to inequitable allocation, water wastage, billing disputes, and poor visibility into individual consumption. Manual valve operation and post-paid estimates are error-prone and difficult to scale. A prepaid, sensor-driven web administration system enforces fair volume allocation per plot while providing transparent consumption records for both farmers and administrators.

## 3. Project Objectives

- Provide a web-based administration portal for registering farmers, assigning flow sensors to farm clusters, and monitoring system-wide water usage.
- Implement a prepaid token allocation model that converts purchased tokens into measurable water volume limits.
- Measure real-time water flow rate and cumulative volume across multiple farm lines using flow sensors and microcontrollers.
- Automate solenoid valve control based on available prepaid token balance and farmer manual shutoff controls.
- Stream live sensor telemetry and token status to farmers via WebSockets and provide historical analytics for administrators.

## 4. Key Features

### Farmer Portal
- **Account Management:** Public registration (with Nigerian `+234` phone validation and user profile fields for RFID and matriculation numbers), login/logout, password change, and email-based password reset. *(Note: RFID and matriculation numbers are stored strictly as user profile information in the web application; a physical RFID reader and RFID-based hardware authentication were not implemented.)*
- **Prepaid Token Recharge:** Purchase or top up water tokens (`1 token = 10 liters`) with live volume preview and a 10-second duplicate-submission cooldown.
- **Real-Time Monitoring Dashboard:** Live flow rate (L/min), cumulative volume (L), remaining volume (L), animated water-level tank indicator, and 30-day usage trend chart.
- **Manual Valve Control:** Remote open/close toggle for the farmer's assigned solenoid valve.
- **Transaction History:** Paginated token purchase and depletion records with record deletion.

### Administrator Portal
- **Overview Dashboard:** Total registered farmers, active sensors, and recent token purchases.
- **Sensor & Cluster Assignment:** Assign or reassign Sensors `1`–`3` to farmers across `Farm A`, `Farm B`, and `Farm C`.
- **User & Admin Management:** View assigned farmers/sensors and create additional administrator accounts via a protected admin-only endpoint.
- **Global Token History:** Searchable (by sensor ID, user ID, email, or username) and filterable (All / Active / Expired) paginated transaction log.
- **Analytics Dashboard:** Visual charts for token distribution, volume usage trends, and active/inactive token breakdown with date-range filtering.

## 5. System Architecture

```text
+-----------------------------------+       I2C (Addr 8)       +----------------------------+
|  Arduino (I2C Slave)              |  <=== 24B Sensor Data => |  NodeMCU ESP8266           |
|  - 3x Flow Sensors (Pins 2, 3, 4) |  <=== 3B Valve Cmd ====> |  (I2C Master: GPIO 4 & 5)  |
|  - 3x Relay Modules (Pins 5, 6, 7)|                          |  - Wi-Fi HTTP Client       |
|  - 3x Solenoid Valves             |                          +-------------+--------------+
+-----------------------------------+                                        |
                                                                HTTP POST /api/flow-data/
                                                                JSON { valve_status }
                                                                             v
+-------------------------------------------------------------------------------------------+
|  Django Web Application (ASGI via Daphne + Django Channels)                               |
|  - REST API (Django REST Framework)     - WebSocket Consumer (/ws/sensor-data/)           |
|  - Token Deduction & Valve Logic        - SQLite (default) / Optional MySQL Database      |
+------------------------------------+-------------------------------------+----------------+
                                     |                                     |
                         WebSockets & REST API                        Web Interface
                                     v                                     v
                     +-------------------------------+     +-------------------------------+
                     |  Farmer Dashboard             |     |  Admin Portal                 |
                     |  - Live Flow & Tank Level     |     |  - Sensor & Farm Assignment   |
                     |  - Token Recharge & Valve Ctrl|     |  - User/Token History & Charts|
                     +-------------------------------+     +-------------------------------+
```

## 6. Hardware Components

Components used in the project and supported by the firmware:

- **Arduino Board** (e.g., Arduino Uno / AVR-compatible board supporting hardware interrupts on pins 2–3, pin-change interrupt on pin 4, and I2C slave mode)
- **NodeMCU ESP8266** (Wi-Fi microcontroller acting as I2C master on GPIO 4 / SDA and GPIO 5 / SCL)
- **3 × Hall-Effect Water Flow Sensors** (calibrated at `7.5` pulses/s per L/min, matching standard YF-S201 sensors)
- **3 × Solenoid Valves** driven via **Active-LOW Relay Modules** (connected to Arduino digital pins `5`, `6`, and `7`)
- **Water Pump** (supplying water to the distribution lines during deployment)
- **Power Configuration:**
  - *Farm-Scale Deployment:* A **100Ah battery** powered the water pump and solenoid valves, while a **lithium battery pack** powered the electronics.
  - *Laboratory-Scale Testing:* A **7.2Ah battery** was used during laboratory-scale testing.
- Jumper wires and direct I2C wiring (SDA, SCL, and shared GND) between the Arduino and NodeMCU.

*(Note: Although the web application records RFID and matriculation numbers as farmer profile attributes, no physical RFID reader hardware or RFID firmware integration was implemented.)*

## 7. Software Technologies & Frameworks

- **Backend:** Python 3.10+, Django 5.1.6, Django REST Framework 3.16, Django Channels, Daphne (ASGI server), `django-cors-headers`, `python-dotenv`
- **Database:** SQLite (default development database; optional MySQL support via `PyMySQL`)
- **Frontend:** Django Templates, HTML5, CSS3, Vanilla JavaScript, Bootstrap 5.3, Bootstrap Icons, Font Awesome 6, Chart.js (loaded via CDN)
- **Embedded Firmware:** Arduino C/C++ (Arduino IDE), ESP8266 Board Package, `Wire`, `PinChangeInterrupt`, `ESP8266WiFi`, `ESP8266HTTPClient`, `ArduinoJson`

## 8. How the System Works

1. **Registration & Assignment:** A farmer registers an account at `/register/`. An administrator logs into the Admin Panel, navigates to **Sensors**, and assigns the farmer a flow sensor (`1`, `2`, or `3`) and farm cluster (`Farm A`, `Farm B`, or `Farm C`).
2. **Token Purchase:** The farmer logs into `/waterflow/` and recharges a token amount. The backend allocates `token_amount × 10` liters to an active `TokenHistory` record.
3. **Continuous Flow Measurement:** The Arduino counts flow-sensor pulses every second and updates each sensor's flow rate and cumulative volume.
4. **Validation & Valve Actuation:** The NodeMCU polls the Arduino over I2C and posts each sensor's reading to `/api/flow-data/`. Django deducts the volume delta from the farmer's active token and replies with `"valve_status": "OPEN"` or `"CLOSE"`.
5. **Automatic & Manual Shutoff:** If the farmer has no active token, the balance reaches `0 L`, or the farmer manually closes the valve on the dashboard, Django returns `"CLOSE"`, prompting the NodeMCU to instruct the Arduino to close that relay.
6. **Live UI Updates:** Django broadcasts updates via Channels (`/ws/sensor-data/`) so the farmer's dashboard reflects live usage and token status.

## 9. Hardware-to-Web Communication

### Arduino ↔ NodeMCU (I2C)
- **Bus Role:** NodeMCU acts as I2C master (`Wire.begin(4, 5)` — SDA = GPIO 4, SCL = GPIO 5); Arduino acts as I2C slave at address `8` (`Wire.begin(8)`).
- **Sensor Telemetry (Arduino → NodeMCU):** On `Wire.requestFrom(8, 24)`, the Arduino transmits 6 packed IEEE-754 32-bit floats (`flowRate1`, `volume1`, `flowRate2`, `volume2`, `flowRate3`, `volume3`).
- **Valve Control (NodeMCU → Arduino):** NodeMCU sends a 3-byte packet: `'V'` (command marker), `sensorId` (`1`–`3`), and `'O'` (OPEN → relay `LOW`) or `'C'` (CLOSE → relay `HIGH`).

### NodeMCU ↔ Django API (HTTP)
- **Endpoint:** `POST http://<SERVER_HOST>:8000/api/flow-data/`
- **Content-Type:** `application/x-www-form-urlencoded`
- **Payload:** `sensor_id=<1|2|3>&flowRate=<L/min>&volume=<L>`
- **Response:** JSON containing `"valve_status": "OPEN"` or `"CLOSE"`, sensor readings, and `token_info`. On any non-200/201 HTTP response or missing `valve_status`, the NodeMCU defaults to closing the valve for safety.

## 10. Water Flow Measurement & Token Calculation

### Flow Sensor Formula (Arduino)
Every `1000 ms`, the Arduino calculates per-sensor flow rate and cumulative volume from interrupt pulse counts:

$$\text{Flow Rate (L/min)} = \frac{\text{pulseCount}}{7.5}$$

$$\text{Volume (L)} \mathrel{+}= \frac{\text{Flow Rate}}{60.0}$$

*(The `7.5` calibration constant matches standard YF-S201 Hall-effect flow sensors: $F\text{ (Hz)} = 7.5 \times Q\text{ (L/min)}$.)*

### Token-to-Volume Conversion (Django Backend)
- **Allocation:** `volume_limit (L) = token_amount × 10`
- **Deduction:** On each incoming sensor reading where `current_volume > last_recorded_volume`:
  - `volume_used_delta = current_volume - last_recorded_volume`
  - `remaining_volume = remaining_volume - volume_used_delta`
- **Depletion Handling:** When `remaining_volume <= 0`, the token is deactivated (`is_active = False`, `end_date = now`), the depleted volume reading is cached in memory to prevent stale readings from reopening the valve, and `valve_status = "CLOSE"` is returned.

## 11. Database & API Overview

### Database Models
- **`base.CustomUser`**: Custom user model (`username`, `email`, `user_id` UUID, `firstname`, `lastname`, `mobile`, `rfid_number`, `matric_number`, `is_admin`, `is_active`).
- **`api.FarmLocation`**: Farm cluster plots (`A` = Farm A, `B` = Farm B, `C` = Farm C), automatically seeded via Django migration `00003_create_farm_locations`.
- **`api.FlowData`**: Associates a `sensor_id` with a `CustomUser` and `FarmLocation`, storing latest `flowRate`, `volume`, `created`, and manual `valve_closed` state.
- **`api.TokenHistory`**: Tracks each token purchase/recharge (`user`, `sensor_id`, `token_amount`, `volume_limit`, `volume_used`, `remaining_volume`, `is_active`, `start_date`, `last_updated`, `end_date`).

### Key Endpoints
| Endpoint | Method | Access | Description |
|---|---|---|---|
| `/api/flow-data/` | `GET`, `POST` | Hardware / API | Receive flow sensor reading, deduct token balance, return `valve_status` (`OPEN`/`CLOSE`) |
| `/api/flow-data/user/` | `GET` | Authenticated Farmer | Retrieve current sensor and active token info |
| `/api/token/recharge/` | `POST` | Authenticated Farmer | Purchase or top up water tokens |
| `/api/token/history/` | `GET` | Authenticated Farmer | List farmer's token transaction history |
| `/api/token/history/<id>/delete/` | `POST` | Authenticated Farmer | Delete a token history record |
| `/api/token/usage-history/` | `GET` | Authenticated User (Owner / Admin) | Fetch 30-day volume usage series for charts |
| `/api/cumulative-volume/` | `GET` | Authenticated User | Fetch cumulative water volume used for a sensor |
| `/api/valve/toggle/` | `POST` | Authenticated Farmer | Manually open or close assigned valve |
| `/api/admin/dashboard/` | `GET` | Admin Only | Admin overview page |
| `/api/admin/users/` | `GET` | Admin Only | Assigned farmers/sensors and admin creation UI |
| `/api/admin/create-admin/` | `POST` | Admin Only | Create a new administrator account |
| `/api/admin/sensor-assignment/` | `GET` | Admin Only | Sensor and farm location assignment UI |
| `/api/admin/assign-sensor/` | `POST` | Admin Only | Assign/reassign a sensor and farm cluster |
| `/api/admin/token-history/` | `GET` | Admin Only | Searchable/filterable global token history |
| `/api/admin/analytics/` | `GET` | Admin Only | Admin analytics dashboard |
| `/api/api/admin/analytics/` | `GET` | Admin Only | JSON metrics and chart series for analytics |
| `/ws/sensor-data/` | `WebSocket` | Browser Clients | Real-time sensor and token updates |

## 12. Installation & Setup Instructions

### Prerequisites
- Python 3.10 or higher
- `pip` and `venv`
- *(Optional)* MySQL server if switching away from the default SQLite database

### Steps

1. **Clone the repository:**
   ```bash
   git clone https://github.com/<your-username>/<your-repo-name>.git
   cd <your-repo-name>
   ```

2. **Configure environment variables:**
   Copy `.env.example` to `.env` in the repository root and configure your local `ALLOWED_HOSTS` (see [Configuration Requirements](#14-configuration-requirements)). `SECRET_KEY` may be left blank for local development with `DEBUG=True`, but you must generate and set a strong random `SECRET_KEY` before switching `DEBUG=False`.

3. **Create and activate a virtual environment:**
   ```bash
   cd web-application
   python -m venv venv
   # Windows (PowerShell)
   .\venv\Scripts\Activate.ps1
   # macOS / Linux
   source venv/bin/activate
   ```

4. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

5. **Run database migrations:**
   ```bash
   python manage.py migrate
   ```
   *(This creates a fresh SQLite database and automatically seeds `Farm A`, `Farm B`, and `Farm C`.)*

6. **Create an initial administrator account:**
   ```bash
   python manage.py createsuperuser
   ```

7. **Run the ASGI development server (required for WebSockets):**
   ```bash
   python manage.py runserver 0.0.0.0:8000
   ```
   *(Because `daphne` is listed first in `INSTALLED_APPS`, `runserver` runs the Daphne ASGI server supporting both HTTP and WebSockets. Binding to `0.0.0.0:8000` allows the NodeMCU on your local network to reach `/api/flow-data/`.)*

## 13. Arduino & NodeMCU Firmware Setup

### Requirements
- [Arduino IDE](https://www.arduino.cc/en/software) (1.8.x or 2.x)
- **ESP8266 Board Package** installed via Arduino IDE Boards Manager (`http://arduino.esp8266.com/stable/package_esp8266com_index.json`)
- **Required Libraries** (install via Arduino Library Manager):
  - `PinChangeInterrupt` (for Arduino sketch)
  - `ArduinoJson` v6.x (for NodeMCU sketch — uses `StaticJsonDocument`)
  - Built-in libraries: `Wire`, `ESP8266WiFi`, `ESP8266HTTPClient`

### Flashing the Arduino
1. Open `Arduino-Codes/ArduinoToNodeMCU/ArduinoToNodeMCU.ino` in Arduino IDE.
2. Connect Flow Sensors 1–3 to digital pins `2`, `3`, and `4`, and active-LOW Valve Relays 1–3 to digital pins `5`, `6`, and `7`.
3. Select your Arduino board and COM port, then click **Upload**.

### Flashing the NodeMCU (ESP8266)
1. Copy `Arduino-Codes/NodeMCUtoWeb/secrets.example.h` to `Arduino-Codes/NodeMCUtoWeb/secrets.h` (which is ignored by Git and required before the sketch will compile).
2. Update `WIFI_SSID`, `WIFI_PASSWORD`, and `SERVER_URL` in `secrets.h`. Supply **only the base server address** without a port number or trailing slash (e.g., `http://192.168.1.100`), because the firmware appends `:8000/api/flow-data/` automatically.
3. Ensure that host IP is listed in Django's `ALLOWED_HOSTS` environment variable.
4. Connect NodeMCU GPIO `4` (D2 / SDA) and GPIO `5` (D1 / SCL) to the Arduino's SDA and SCL pins with a shared GND.
5. Open `Arduino-Codes/NodeMCUtoWeb/NodeMCUtoWeb.ino`, select **NodeMCU 1.0 (ESP-12E Module)** and the COM port, then click **Upload**.

### Hardware Testing & System Limitations
- **Local Firmware Secrets Required:** `NodeMCUtoWeb.ino` requires a locally created `secrets.h` file (copied from `secrets.example.h`) containing your Wi-Fi credentials and server base URL before it can be compiled in Arduino IDE.
- **Server Address Format:** `SERVER_URL` must be a base URL without a port or trailing slash (e.g., `http://192.168.1.100`), as the sketch appends `:8000/api/flow-data/`.
- **Network Connectivity:** The NodeMCU and the machine running Django must reside on the same reachable network with TCP port `8000` accessible through any host firewall.
- **Token Recharge Scope:** Token recharge does not currently integrate an external payment gateway; token credits are added directly through the application's recharge workflow.
- **Hardware API Security:** The `/api/flow-data/` endpoint does not currently enforce hardware API-key authentication. It is intended for trusted private-network deployments and should not be exposed publicly on the internet without additional protection.
- **Verification Scope:** While the physical hardware prototype was developed and tested during the original final-year project, physical hardware testing and Arduino IDE compilation were not re-executed during the automated repository preparation and verification in this development environment.

## 14. Configuration Requirements

All sensitive and environment-specific settings are read from environment variables (see `.env.example`):

- `SECRET_KEY`: Django cryptographic signing key (required when `DEBUG=False`).
- `DEBUG`: `True` for local development, `False` for production.
- `ALLOWED_HOSTS`: Comma-separated permitted hosts/IPs (include `localhost`, `127.0.0.1`, and the host's LAN IP for NodeMCU requests).
- `CSRF_TRUSTED_ORIGINS` / `CORS_ALLOWED_ORIGINS` / `CORS_ALLOW_ALL_ORIGINS`: Permitted cross-origin and CSRF origins (`CORS_ALLOW_ALL_ORIGINS` defaults to `False`).
- `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE`: Set to `True` in HTTPS production deployments.
- `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`: SMTP settings required for password-reset emails.
- `DB_ENGINE`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`: Defaults to `sqlite3` (`db.sqlite3`). Set `DB_ENGINE=mysql` with valid credentials for optional MySQL support.

## 15. Screenshots & Documentation

- Supplementary diagrams and documentation can be placed in [`docs/`](docs/README.md).
- Application and hardware screenshots can be placed in [`screenshots/`](screenshots/README.md) and embedded here once captured.

## 16. Contributors

This final-year project was developed collaboratively by two contributors.


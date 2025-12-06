# IoT Telematics Datalogger & Dashboard

A full-stack IoT solution designed to monitor heavy machinery (specifically Ammann Pavers and Rollers). This project consists of an **ESP32-based firmware** for data acquisition via CAN Bus and a **Flask-based web platform** for real-time telemetry, fleet management, and data analysis.

## 🚀 Features

### Web Platform (Dashboard)
* **Global Fleet Overview:** Interactive map (Leaflet.js) displaying the real-time location of all devices.
* **Real-Time Telemetry:** Live updates via WebSockets (Socket.IO) for Engine RPM, Fuel Rate, Coolant Temp, and more.
* **User Management:**
    * Secure Login/Registration with JWT authentication.
    * **Admin Panel** to approve/activate new user accounts.
    * Password reset flow (via Email) and profile management.
* **Data Logging:** View and download historical logs (CSV/Excel) organized by date and device.
* **Responsive Design:** Built with Tailwind CSS for mobile and desktop compatibility.

### Hardware (ESP32 Firmware)
* **Dual CAN Bus Support:** Configurable for Engine CAN (J1939) and TTC/Machine CAN.
* **Offline Logging:** Logs data to an SD Card when network is unavailable.
* **Configuration Portal:** ESP32 acts as a WiFi Access Point (AP) to configure Machine Name, VIN, and Baud Rates via a web interface.
* **Connectivity:** Handles switching between Configuration Mode (WiFi AP) and Operational Mode (GSM/MQTT data transmission).

---

## 🛠️ Tech Stack

* **Hardware:** ESP32-S3 (Arduino Framework / C++), FreeRTOS.
* **Backend:** Python 3.11, Flask, Flask-SocketIO, SQLAlchemy (SQLite/PostgreSQL).
* **Frontend:** HTML5, Tailwind CSS, Vanilla JavaScript, Leaflet.js.
* **Database:** SQLite (Local Development), PostgreSQL (Production).
* **Deployment:** Docker, Gunicorn, Render.com ready.

---

## 📂 Project Structure

```text
├── arduino file/          # ESP32 Firmware code (.ino)
│   └── ESP32_Data logger_V1.ino
├── backend/               # Flask Application Server
│   ├── app.py             # Main application entry point
│   ├── models.py          # Database models (User, Device, LogFolder)
│   ├── init_db.py         # Script to reset/initialize database
│   ├── seed_db.py         # Script to populate DB with dummy data
│   └── migrations/        # Alembic database migrations
├── static/                # Static assets (images, SVGs)
├── templates/             # (HTML files are currently in root, served by Flask)
├── config.js              # Frontend configuration (API URLs)
├── HomePage.html          # Main Dashboard
├── admin.html             # Admin management panel
├── login.html             # Auth pages
└── requirements.txt       # Python dependencies

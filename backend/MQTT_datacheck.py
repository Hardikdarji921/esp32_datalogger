import json
import threading
from flask import Flask, render_template_string
from flask_socketio import SocketIO
import paho.mqtt.client as mqtt

# ==========================================
# CONFIGURATION
# ==========================================
MQTT_BROKER = "broker.emqx.io"
MQTT_PORT = 1883  # Standard TCP port (Connecting to same broker as your 8084 WSS)
MQTT_TOPIC = "Datalogger/Device_1/Data"
FLASK_PORT = 5000

# ==========================================
# FLASK & SOCKETIO SETUP
# ==========================================
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ==========================================
# HTML TEMPLATE (Embedded for single-file usage)
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vehicle Live Telemetry</title>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        :root {
            --primary: #2c3e50;
            --accent: #3498db;
            --success: #27ae60;
            --danger: #e74c3c;
            --card-bg: #ffffff;
            --bg: #f4f7f6;
        }
        body { font-family: 'Segoe UI', sans-serif; background-color: var(--bg); margin: 0; padding: 20px; }
        
        .header { text-align: center; margin-bottom: 30px; }
        .header h1 { color: var(--primary); margin: 0; }
        .status-badge { 
            display: inline-block; padding: 5px 15px; border-radius: 20px; 
            color: white; font-weight: bold; margin-top: 10px;
        }
        .status-on { background-color: var(--success); }
        .status-off { background-color: var(--danger); }

        .dashboard-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            max-width: 1200px;
            margin: 0 auto;
        }

        .card {
            background: var(--card-bg);
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05);
            display: flex;
            align-items: center;
            transition: transform 0.2s;
        }
        .card:hover { transform: translateY(-3px); }
        
        .icon-box {
            width: 50px; height: 50px;
            background: rgba(52, 152, 219, 0.1);
            border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            margin-right: 15px;
            color: var(--accent);
            font-size: 1.5rem;
        }

        .data-content h3 { margin: 0; font-size: 0.9rem; color: #7f8c8d; text-transform: uppercase; }
        .data-content p { margin: 5px 0 0; font-size: 1.8rem; font-weight: bold; color: var(--primary); }
        .unit { font-size: 1rem; color: #95a5a6; }

        .full-width { grid-column: 1 / -1; }
        
        .map-link {
            display: inline-block;
            margin-top: 10px;
            text-decoration: none;
            color: var(--accent);
            font-weight: bold;
        }
        
        .footer { text-align: center; margin-top: 30px; color: #95a5a6; font-size: 0.9rem; }
        
        /* Specific Colors */
        .icon-fuel { color: #e67e22; background: rgba(230, 126, 34, 0.1); }
        .icon-rpm { color: #e74c3c; background: rgba(231, 76, 60, 0.1); }
        .icon-batt { color: #f1c40f; background: rgba(241, 196, 15, 0.1); }
    </style>
</head>
<body>

    <div class="header">
        <h1><i class="fas fa-truck-monster"></i> Vehicle Live Dashboard</h1>
        <div id="status-container">
            <span id="conn-status" class="status-badge status-off">WAITING FOR DATA...</span>
        </div>
        <div style="margin-top: 10px; color: #7f8c8d;">
            Last Updated: <span id="last-updated">--</span>
        </div>
    </div>

    <div class="dashboard-grid">
        <!-- RPM -->
        <div class="card">
            <div class="icon-box icon-rpm"><i class="fas fa-tachometer-alt"></i></div>
            <div class="data-content">
                <h3>Engine RPM</h3>
                <p><span id="rpm">0</span> <span class="unit">RPM</span></p>
            </div>
        </div>

        <!-- Fuel -->
        <div class="card">
            <div class="icon-box icon-fuel"><i class="fas fa-gas-pump"></i></div>
            <div class="data-content">
                <h3>Fuel Level</h3>
                <p><span id="fuel">0</span> <span class="unit">%</span></p>
            </div>
        </div>

        <!-- Temperature -->
        <div class="card">
            <div class="icon-box"><i class="fas fa-thermometer-half"></i></div>
            <div class="data-content">
                <h3>Coolant Temp</h3>
                <p><span id="temp">0</span> <span class="unit">°C</span></p>
            </div>
        </div>

        <!-- Battery -->
        <div class="card">
            <div class="icon-box icon-batt"><i class="fas fa-car-battery"></i></div>
            <div class="data-content">
                <h3>Battery Voltage</h3>
                <p><span id="batt">0</span> <span class="unit">mV</span></p>
            </div>
        </div>

        <!-- Torque -->
        <div class="card">
            <div class="icon-box"><i class="fas fa-cog"></i></div>
            <div class="data-content">
                <h3>Torque</h3>
                <p><span id="torque">0</span> <span class="unit">%</span></p>
            </div>
        </div>

        <!-- DEF Level -->
        <div class="card">
            <div class="icon-box"><i class="fas fa-tint"></i></div>
            <div class="data-content">
                <h3>DEF Level</h3>
                <p><span id="def">0</span> <span class="unit">%</span></p>
            </div>
        </div>

        <!-- Engine Hours -->
        <div class="card">
            <div class="icon-box"><i class="fas fa-clock"></i></div>
            <div class="data-content">
                <h3>Engine Hours</h3>
                <p><span id="eng_hours">0</span> <span class="unit">h</span></p>
            </div>
        </div>

        <!-- Location -->
        <div class="card full-width">
            <div class="icon-box"><i class="fas fa-map-marker-alt"></i></div>
            <div class="data-content">
                <h3>GPS Location</h3>
                <p style="font-size: 1.2rem;">
                    Lat: <span id="lat">--</span>, Lon: <span id="lon">--</span>
                </p>
                <a id="maps-link" href="#" target="_blank" class="map-link">View on Google Maps &rarr;</a>
            </div>
        </div>
    </div>

    <div class="footer">
        Connected to Broker: <strong>broker.emqx.io</strong> | Topic: <strong>Datalogger/Device_1/Data</strong>
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <script>
        const socket = io();

        // Listen for 'mqtt_data' event from Python
        socket.on('mqtt_data', function(msg) {
            console.log("Received Data:", msg);
            
            // Update Text Fields
            document.getElementById('rpm').innerText = msg.rpm;
            document.getElementById('fuel').innerText = msg.fuel_level;
            document.getElementById('temp').innerText = msg.temp;
            document.getElementById('batt').innerText = msg.batt;
            document.getElementById('torque').innerText = msg.torque;
            document.getElementById('def').innerText = msg.def_level;
            document.getElementById('eng_hours').innerText = msg.eng_hours;
            document.getElementById('lat').innerText = msg.lat;
            document.getElementById('lon').innerText = msg.lon;
            document.getElementById('last-updated').innerText = msg.time;

            // Update Maps Link
            const mapUrl = `https://www.google.com/maps?q=${msg.lat},${msg.lon}`;
            document.getElementById('maps-link').href = mapUrl;

            // Update Status Badge
            const statusBadge = document.getElementById('conn-status');
            statusBadge.innerText = msg.status;
            if(msg.status === "ON") {
                statusBadge.className = "status-badge status-on";
            } else {
                statusBadge.className = "status-badge status-off";
            }
        });
    </script>
</body>
</html>
"""

# ==========================================
# MQTT HANDLERS
# ==========================================
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"Connected to MQTT Broker! Subscribing to {MQTT_TOPIC}...")
        client.subscribe(MQTT_TOPIC)
    else:
        print(f"Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode()
        print(f"Received: {payload}")
        
        # Parse JSON
        data = json.loads(payload)
        
        # Send data to Web Page via WebSocket
        socketio.emit('mqtt_data', data)
        
    except json.JSONDecodeError:
        print("Error: Failed to decode JSON")
    except Exception as e:
        print(f"Error processing message: {e}")

# ==========================================
# MAIN EXECUTION
# ==========================================
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

def start_mqtt():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    
    # Note: We use port 1883 (TCP) for Python backend. 
    # It connects to the same EMQX broker as port 8084 (WSS).
    print("Connecting to MQTT Broker...")
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_forever()
    except Exception as e:
        print(f"Connection Failed: {e}")

if __name__ == '__main__':
    # Run MQTT in a background thread
    mqtt_thread = threading.Thread(target=start_mqtt)
    mqtt_thread.daemon = True
    mqtt_thread.start()
    
    # Run Flask App
    print(f"Starting Web Server on port {FLASK_PORT}...")
    socketio.run(app, host='0.0.0.0', port=FLASK_PORT, debug=True, use_reloader=False)
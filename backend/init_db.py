
from app import app, db, Device, User, LogFolder, LogFile
from werkzeug.security import generate_password_hash
import json

# This is the new, detailed data payload from your ESP32
device_1_params = {
    "timestamp": 1730707200,
    "last_sync_utc": "2025-11-04T12:00:00Z",
    "uptime_sec": 45600,
    "gps_fix": True,
    "lat": 40.712800,
    "lon": -74.006000,
    "machine_name": "Field Harvester Alpha",
    "vin_number": "J1939-XYZ-12345",
    "sd_free_mb": 18500,
    "last_sync_duration_ms": 1250,
    "engine_rpm_spn": 1850,
    "accel_pos_pc": 25.5,
    "fuel_rate_lh": 50.0,
    "coolant_temp_c": 90.5,
    "oil_pressure_kpa": 400,
    "total_engine_hours_h": 1000.50,
    "daily_engine_hours_h": 3.75,
    "fuel_level_pc": 75.2,
    "def_level_pc": 55.0,
    "sw_major_version": 4,
    "sw_minor_version": 2,
    "sw_service_pack": 1,
    "sw_hot_fix": 5,
    "dtcs": "Engine, DTCs: None | TTC_MCU, DTCs: 8212-3 (OC:1)",
    "bus": "engine"
}

# This is the old data for the other devices, for variety
device_2_params = { "Engine Hours": 756.80, "Altitude": 45.5, "Speed Over Ground": 0.00, "Tire Pressure": 32, "Oil Temp": 95 }
device_3_params = { "Engine Hours": 510.00, "Altitude": 15.0, "Speed Over Ground": 0.00 }

mock_devices_data = [
    { 
        "id": 1, "name": "V-2207", "serial": "JMR01-CSV-V2", "status": "Online", "lat": 23.0225, "lon": 72.5714,
        "firmware": "3.04.1-RC", "config": "UNITSCANNER_2", "maxSpace": 29.82, "freeSpace": 1.5,
        "parameters": device_1_params, # <-- Use the new detailed parameters
        "displayParameters": ["engine_rpm_spn", "accel_pos_pc", "fuel_rate_lh"], # Default parameters to show
        "machine_model": "AP550", "machine_type": "CEV_V"
    },
    { 
        "id": 2, "name": "V-2336", "serial": "JPR08-CSV-V", "status": "Online", "lat": 22.3072, "lon": 73.1812,
        "firmware": "3.03.0-RC", "config": "DEFAULT_CFG", "maxSpace": 29.82, "freeSpace": 10.2,
        "parameters": device_2_params,
        "displayParameters": ["Engine Hours", "Altitude", "Speed Over Ground"],
        "machine_model": "ARS110_2", "machine_type": "CEV_V"
    },
    { 
        "id": 3, "name": "V-2209", "serial": "JMR02-CSV-V1", "status": "Offline", "lat": 22.5726, "lon": 88.3639,
        "firmware": "2.95.5-STABLE", "config": "LEGACY_MODE", "maxSpace": 14.9, "freeSpace": 0.8,
        "parameters": device_3_params,
        "displayParameters": ["Engine Hours", "Altitude", "Speed Over Ground"],
        "machine_model": "AP600", "machine_type": "CEV_IV"
    }
]

with app.app_context():
    print("Dropping all tables...")
    db.drop_all()
    print("Creating all tables...")
    db.create_all()

    # --- Add Devices ---
    print("Adding device data...")
    devices = []
    for device_data in mock_devices_data:
        new_device = Device(
            id=device_data["id"], name=device_data["name"], serial=device_data["serial"],
            status=device_data["status"], lat=device_data["lat"], lon=device_data["lon"],
            firmware=device_data["firmware"], config=device_data["config"], maxSpace=device_data["maxSpace"],
            freeSpace=device_data["freeSpace"], parameters=json.dumps(device_data["parameters"]),
            displayParameters=json.dumps(device_data["displayParameters"]),
            machine_model=device_data["machine_model"], machine_type=device_data["machine_type"]  
        )
        db.session.add(new_device)
        devices.append(new_device)
    
    # --- Add Users ---
    print("Adding user data...")
    admin_pass_hash = generate_password_hash("adminpassword")
    admin_user = User(username="admin", password_hash=admin_pass_hash, role="admin", is_active=True, full_name="Administrator", email="admin@example.com", company="Admin Corp")
    db.session.add(admin_user)

    hardik_pass_hash = generate_password_hash("testpassword123")
    hardik_user = User(username="hardik", password_hash=hardik_pass_hash, role="user", is_active=True, full_name="Hardik", email="hardik@example.com", company="Ammann Group")
    db.session.add(hardik_user)
    
    # --- Add Log Folders and Files ---
    print("Adding log data...")
    # Logs for Device 1 (V-2207)
    folder1 = LogFolder(name="20251009", device_id=devices[0].id)
    folder2 = LogFolder(name="20251008", device_id=devices[0].id)
    db.session.add(folder1)
    db.session.add(folder2)
    # Must commit here so folders get an ID before we add files to them
    db.session.commit() 

    file1 = LogFile(name="arx32.rxd", size="105.2 MB", modified="08:15 AM", folder_id=folder1.id)
    file2 = LogFile(name="events.log", size="1.1 MB", modified="08:16 AM", folder_id=folder1.id)
    file3 = LogFile(name="arx32.rxd", size="98.7 MB", modified="11:30 AM", folder_id=folder2.id)
    db.session.add_all([file1, file2, file3])
    
    # Commit all changes to the database
    db.session.commit()
    print("Database initialized successfully!")


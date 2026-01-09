from app import app, db, Device, User, LogFolder, LogFile
from werkzeug.security import generate_password_hash
import json

# IMPORTANT: This script ASSUMES your tables are already created by 'flask db upgrade'.
# It does NOT delete anything.

# Data for devices
mock_devices_data = [
    { 
        "id": 1, "name": "V-2207", "serial": "JMR01-CSV-V2", "status": "Online", "lat": 23.0225, "lon": 72.5714,
        "firmware": "3.04.1-RC", "config": "UNITSCANNER_2", "maxSpace": 29.82, "freeSpace": 1.5,
        "parameters": { "Engine Hours": 864.80, "Altitude": 76.2, "Speed Over Ground": 55.00, "Latitude": 23.0225, "Longitude": 72.5714, "Quality": "Good" },
        "displayParameters": ["Engine Hours", "Altitude", "Speed Over Ground"] 
    },
    { 
        "id": 2, "name": "V-2336", "serial": "JPR08-CSV-V", "status": "Online", "lat": 22.3072, "lon": 73.1812,
        "firmware": "3.03.0-RC", "config": "DEFAULT_CFG", "maxSpace": 29.82, "freeSpace": 10.2,
        "parameters": { "Engine Hours": 756.80, "Altitude": 45.5, "Speed Over Ground": 0.00, "Tire Pressure": 32, "Oil Temp": 95 },
        "displayParameters": ["Engine Hours", "Altitude", "Speed Over Ground"] 
    },
]

with app.app_context():
    print("Seeding database with initial data...")

    # Check if admin user already exists to prevent duplicates
    if User.query.filter_by(username='admin').first() is None:
        # Add Users
        admin_pass_hash = generate_password_hash("adminpassword")
        admin_user = User(username="admin", password_hash=admin_pass_hash, role="admin", is_active=True, full_name="Administrator", email="admin@example.com", company="Admin Corp")
        db.session.add(admin_user)

        hardik_pass_hash = generate_password_hash("testpassword123")
        hardik_user = User(username="hardik", password_hash=hardik_pass_hash, role="user", is_active=True, full_name="Hardik", email="hardik@example.com", company="Ammann Group")
        db.session.add(hardik_user)
        print("Admin and user seeded.")
    else:
        print("Admin user already exists, skipping user seeding.")

    # Add Devices
    devices = []
    if Device.query.count() == 0:
        for device_data in mock_devices_data:
            new_device = Device(id=device_data["id"], name=device_data["name"], serial=device_data["serial"], status=device_data["status"], lat=device_data["lat"], lon=device_data["lon"], firmware=device_data["firmware"], config=device_data["config"], maxSpace=device_data["maxSpace"], freeSpace=device_data["freeSpace"], parameters=json.dumps(device_data["parameters"]), displayParameters=json.dumps(device_data["displayParameters"]))
            db.session.add(new_device)
            devices.append(new_device)
        print("Devices seeded.")
    else:
        print("Devices already exist, skipping device seeding.")
        devices = Device.query.all() # Load existing devices to add logs to them

    # Add Log Folders and Files
    if LogFolder.query.count() == 0 and len(devices) > 0:
        folder1 = LogFolder(name="20251009", device_id=devices[0].id)
        folder2 = LogFolder(name="20251008", device_id=devices[0].id)
        db.session.add(folder1)
        db.session.add(folder2)
        db.session.commit() 

        file1 = LogFile(name="arx32.rxd", size="105.2 MB", modified="08:15 AM", folder_id=folder1.id)
        file2 = LogFile(name="events.log", size="1.1 MB", modified="08:16 AM", folder_id=folder1.id)
        file3 = LogFile(name="arx32.rxd", size="98.7 MB", modified="11:30 AM", folder_id=folder2.id)
        db.session.add_all([file1, file2, file3])
        print("Log data seeded.")
    else:
        print("Log data already exists, skipping log seeding.")
    
    db.session.commit()
    print("Seeding complete.")
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
import werkzeug.exceptions
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
import json
import jwt
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask_socketio import SocketIO, emit
from flask_migrate import Migrate
import os
from flask import send_from_directory
import urllib.parse

# ### NEW: Import Supabase Client ###
from supabase import create_client, Client

# --- ROBUST PATH CONFIGURATION ---
basedir = os.path.abspath(os.path.dirname(__file__))
static_dir = os.path.join(os.path.dirname(basedir), 'static')

app = Flask(__name__, static_folder=static_dir, static_url_path='/static')

CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# --- GLOBAL ERROR HANDLER ---
@app.errorhandler(Exception)
def handle_exception(e):
    """Return JSON instead of HTML for any application-level error."""
    if isinstance(e, (werkzeug.exceptions.HTTPException,)):
        response = e.get_response()
        response.data = json.dumps({
            "code": e.code,
            "name": e.name,
            "message": e.description,
        })
        response.content_type = "application/json"
        return response

    response = {
        "message": f"An internal server error occurred: {str(e)}",
        "code": 500,
        "name": "Internal Server Error"
    }
    return jsonify(response), 500


# --- CONFIGURATION ---
app.config['SECRET_KEY'] = 'your-super-secret-key-that-no-one-should-know'

# Database Connection (Your correctly configured Pooler URL)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres.qditrhotokqilstiswex:Hardik%40123@aws-1-ap-northeast-2.pooler.supabase.com:6543/postgres'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Mail Config
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'espdatalogger0@gmail.com' 
app.config['MAIL_PASSWORD'] = 'cndofvbtuxamnvom'

# ### NEW: Supabase Storage Config ###
# You can find these in Supabase Dashboard > Settings > API
SUPABASE_URL = "https://qditrhotokqilstiswex.supabase.co" 
SUPABASE_KEY = "YOUR_SUPABASE_SERVICE_ROLE_KEY" # <--- REPLACE THIS with your actual Service Role Key!

# Initialize Supabase Client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

db = SQLAlchemy(app)
mail = Mail(app)
migrate = Migrate(app, db)

# --- DATABASE MODELS ---
class Device(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    serial = db.Column(db.String(120), unique=True, nullable=False)
    status = db.Column(db.String(50), nullable=False)
    lat = db.Column(db.Float, nullable=False)
    lon = db.Column(db.Float, nullable=False)
    firmware = db.Column(db.String(80))
    config = db.Column(db.String(80))
    maxSpace = db.Column(db.Float)
    freeSpace = db.Column(db.Float)
    parameters = db.Column(db.Text)
    displayParameters = db.Column(db.Text)
    machine_model = db.Column(db.String(50))
    machine_type = db.Column(db.String(50))  
    log_folders = db.relationship('LogFolder', backref='device', lazy=True, cascade="all, delete-orphan")
    last_sync = db.Column(db.DateTime) 

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='proto')  # admin, production, proto, custom
    full_name = db.Column(db.String(120))
    email = db.Column(db.String(120), unique=True, nullable=False)
    company = db.Column(db.String(120))
    dob = db.Column(db.String(50))
    birth_place = db.Column(db.String(120))
    mobile_number = db.Column(db.String(50))
    address = db.Column(db.String(255))
    reset_token = db.Column(db.String(100), unique=True)
    reset_token_expiration = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    last_login = db.Column(db.DateTime)
    
class LogFolder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    device_id = db.Column(db.Integer, db.ForeignKey('device.id'), nullable=False)
    files = db.relationship('LogFile', backref='folder', lazy=True, cascade="all, delete-orphan")

class LogFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    size = db.Column(db.String(50))
    modified = db.Column(db.String(50))
    folder_id = db.Column(db.Integer, db.ForeignKey('log_folder.id'), nullable=False)


class UserMachine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    device_id = db.Column(db.Integer, db.ForeignKey('device.id'), nullable=False)
    visible_data = db.Column(db.Text)  # JSON string of visible data fields
    visible_logs = db.Column(db.Text)  # JSON string of visible log folders/files


# --- DECORATORS ---
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('x-access-token')
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = User.query.get(data['user_id'])
            if current_user is None:
                return jsonify({'message': 'User not found!'}), 401
        except Exception as e:
            return jsonify({'message': 'Token is invalid!', 'error': str(e)}), 401
        return f(current_user, *args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(current_user, *args, **kwargs):
        if current_user.role != 'admin':
            return jsonify({'message': 'Admin privileges required!'}), 403
        return f(current_user, *args, **kwargs)
    return decorated

# --- ROUTES ---

@app.route("/api/profile", methods=['GET'])
@token_required
def get_profile(current_user):
    return jsonify({
        'full_name': current_user.full_name, 'email': current_user.email,
        'company': current_user.company, 'dob': current_user.dob,
        'birth_place': current_user.birth_place, 'mobile_number': current_user.mobile_number,
        'address': current_user.address
    })

@app.route("/api/profile", methods=['PUT'])
@token_required
def update_profile(current_user):
    data = request.get_json()
    try:
        current_user.full_name = data.get('full_name', current_user.full_name)
        current_user.dob = data.get('dob', current_user.dob)
        current_user.birth_place = data.get('birth_place', current_user.birth_place)
        current_user.mobile_number = data.get('mobile_number', current_user.mobile_number)
        current_user.address = data.get('address', current_user.address)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500
    return jsonify({'message': 'Profile updated successfully!'})

@app.route("/api/change-password", methods=['POST'])
@token_required
def change_password(current_user):
    data = request.get_json()
    if not data or 'current_password' not in data or 'new_password' not in data:
        return jsonify({'message': 'Current and new passwords are required.'}), 400
    if not check_password_hash(current_user.password_hash, data['current_password']):
        return jsonify({'message': 'Invalid current password.'}), 401
    current_user.password_hash = generate_password_hash(data['new_password'])
    db.session.commit()
    return jsonify({'message': 'Password changed successfully.'})

@app.route('/<path:filename>')
def serve_html(filename):
    return send_from_directory('../', filename)

@app.route('/')
def root():
    return send_from_directory('../', 'login.html')

@app.route('/HomePage.html')
def home():
    return send_from_directory('../', 'HomePage.html')

@app.route("/api/live-data", methods=['POST'])
def receive_live_data():
    data = request.get_json()
    if not data or 'device_id' not in data:
        return jsonify({"message": "Invalid data"}), 400
    
    print(f"Received data from device {data['device_id']}: {data}")
    socketio.emit(f'device_update_{data["device_id"]}', data)
    return jsonify({"message": "Data received"}), 200

# ### NEW: Storage Upload Endpoint ###
@app.route("/api/upload-log", methods=['POST'])
def upload_log():
    # 1. Check if file is present in request
    if 'file' not in request.files:
        return jsonify({"message": "No file part in the request"}), 400
    
    file = request.files['file']
    filename = file.filename
    
    # 2. Upload to Supabase Storage
    try:
        file_content = file.read()
        bucket_name = "device-logs" # Make sure this bucket exists in Supabase!
        
        # This uploads the file to the bucket
        # Note: You might want to prefix filename with device_id to organize files
        # e.g., path = f"{device_id}/{filename}"
        response = supabase.storage.from_(bucket_name).upload(
            path=filename, 
            file=file_content,
            file_options={"content-type": "text/csv"} # Adjust mime-type if needed
        )
        
        return jsonify({"message": "Upload successful", "path": filename}), 200
        
    except Exception as e:
        print(f"Storage Upload Error: {str(e)}")
        return jsonify({"message": f"Storage upload failed: {str(e)}"}), 500


@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json()
    username, password = data.get('username'), data.get('password')
    full_name, email = data.get('full_name'), data.get('email')
    if not all([username, password, full_name, email]):
        return jsonify({"message": "Username, password, full name, and email are required"}), 400
    if User.query.filter((User.username == username) | (User.email == email)).first():
        return jsonify({"message": "Username or email already exists"}), 409
    
    hashed_password = generate_password_hash(password)
    new_user = User(username=username, password_hash=hashed_password, full_name=full_name, email=email, company=data.get('company'), role='proto')
    db.session.add(new_user)
    db.session.commit()
    return jsonify({"message": "Registration successful! You can now log in."}), 201

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    user = User.query.filter_by(email=data.get('email')).first() 
    if not user or not check_password_hash(user.password_hash, data.get('password')):
        return jsonify({"message": "Invalid credentials"}), 401
    user.last_login = datetime.now(timezone.utc)
    db.session.commit()
    payload = {'user_id': user.id, 'role': user.role, 'exp': datetime.now(timezone.utc) + timedelta(hours=24)}
    token = jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')
    return jsonify({'token': token})

@app.route("/api/forgot-password", methods=["POST", "OPTIONS"])
def forgot_password():
    if request.method == 'OPTIONS': return jsonify({'status': 'ok'}), 200
    
    data = request.get_json()
    email = data.get('email')
    user = User.query.filter_by(email=email).first()

    if not user:
        return jsonify({'message': 'This email address is not registered.'}), 404

    reset_token = secrets.token_urlsafe(32)
    expiration = datetime.now(timezone.utc) + timedelta(minutes=15)
    
    user.reset_token = reset_token
    user.reset_token_expiration = expiration
    db.session.commit()

    FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://127.0.0.1:5500')
    reset_url = f"{FRONTEND_URL}/reset_password.html?token={reset_token}"

    msg = Message('Password Reset Request', sender=app.config['MAIL_USERNAME'], recipients=[user.email])
    msg.html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
            .container {{ width: 90%; max-width: 600px; margin: 20px auto; padding: 30px; }}
            .button {{ display: inline-block; padding: 12px 25px; background-color: #007bff; color: #fff; text-decoration: none; border-radius: 5px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h3>Password Reset Request</h3>
            <p>Hello {user.full_name},</p>
            <p>Click below to reset your password:</p>
            <a href="{reset_url}" class="button">Reset Your Password</a>
        </div>
    </body>
    </html>
    """
    
    try:
        mail.send(msg)
    except Exception as e:
        print(f"Email sending failed: {str(e)}")
        return jsonify({'message': 'Could not send email.'}), 500
        
    return jsonify({'message': 'A password reset link has been sent to your email.'})


@app.route("/api/reset-password", methods=["POST", "OPTIONS"])
def reset_password():
    if request.method == 'OPTIONS': return jsonify({'status': 'ok'}), 200
    
    data = request.get_json()
    token = data.get('token')
    new_password = data.get('password')

    if not token or not new_password:
        return jsonify({'message': 'Token and new password are required.'}), 400

    user = User.query.filter_by(reset_token=token).first()
    
    if not user or user.reset_token_expiration < datetime.now(timezone.utc):
        return jsonify({'message': 'Token is invalid or has expired. Please request a new one.'}), 401
    
    user.password_hash = generate_password_hash(new_password)
    user.reset_token = None
    user.reset_token_expiration = None
    db.session.commit()

    return jsonify({'message': 'Password has been reset successfully.'})
        
        
@app.route("/api/admin/users", methods=['GET'])
@token_required
@admin_required
def get_all_users(current_user):
    users = User.query.all()
    output = []
    for u in users:
        output.append({
            'id': u.id, 'username': u.username, 'role': u.role, 
            'full_name': u.full_name, 'email': u.email, 'company': u.company,
            'dob': u.dob, 'birth_place': u.birth_place, 'mobile_number': u.mobile_number, 'address': u.address,
            'created_at': u.created_at.isoformat() if u.created_at else None,
            'last_login': u.last_login.isoformat() if u.last_login else None
        })
    return jsonify(output)

@app.route("/api/admin/users/<int:user_id>", methods=['DELETE'])
@token_required
@admin_required
def delete_user(current_user, user_id):
    user = User.query.get(user_id)
    if not user: return jsonify({'message': 'User not found'}), 404
    if user.role == 'admin': return jsonify({'message': 'Cannot delete an admin account.'}), 403
    db.session.delete(user)
    db.session.commit()
    return jsonify({'message': f'User {user.username} deleted'})

@app.route("/api/admin/users/<int:user_id>/role", methods=['PUT'])
@token_required
@admin_required
def update_user_role(current_user, user_id):
    user = User.query.get(user_id)
    if not user: return jsonify({'message': 'User not found'}), 404
    
    data = request.get_json()
    new_role = data.get('role')
    if new_role not in ['admin', 'production', 'proto', 'custom']:
        return jsonify({'message': 'Invalid role'}), 400
    
    user.role = new_role
    db.session.commit()
    return jsonify({'message': f'User role updated to {new_role}'})

@app.route("/api/admin/users/<int:user_id>/permissions", methods=['GET', 'PUT'])
@token_required
@admin_required
def manage_user_permissions(current_user, user_id):
    user = User.query.get(user_id)
    if not user: return jsonify({'message': 'User not found'}), 404
    
    if request.method == 'GET':
        permissions = UserMachine.query.filter_by(user_id=user_id).all()
        result = []
        for perm in permissions:
            device = Device.query.get(perm.device_id)
            result.append({
                'device_id': perm.device_id,
                'device_name': device.name if device else 'Unknown',
                'visible_data': json.loads(perm.visible_data or '[]'),
                'visible_logs': json.loads(perm.visible_logs or '[]')
            })
        return jsonify(result)
    
    elif request.method == 'PUT':
        data = request.get_json()
        device_id = data.get('device_id')
        visible_data = data.get('visible_data', [])
        visible_logs = data.get('visible_logs', [])
        
        # Remove existing permission for this device
        UserMachine.query.filter_by(user_id=user_id, device_id=device_id).delete()
        
        # Add new permission
        if visible_data or visible_logs:
            new_perm = UserMachine(
                user_id=user_id, 
                device_id=device_id, 
                visible_data=json.dumps(visible_data),
                visible_logs=json.dumps(visible_logs)
            )
            db.session.add(new_perm)
        
        db.session.commit()
        return jsonify({'message': 'Permissions updated'})


@app.route("/api/devices")
@token_required
def get_devices(current_user):
    all_devices = Device.query.all()
    result = []
    
    if current_user.role == 'admin':
        # Admin sees all devices
        devices = all_devices
    elif current_user.role == 'proto':
        # Proto sees all devices
        devices = all_devices
    elif current_user.role == 'production':
        # Production sees only assigned devices
        user_machines = UserMachine.query.filter_by(user_id=current_user.id).all()
        device_ids = [um.device_id for um in user_machines]
        devices = Device.query.filter(Device.id.in_(device_ids)).all()
    elif current_user.role == 'custom':
        # Custom sees assigned devices with filtered data
        user_machines = UserMachine.query.filter_by(user_id=current_user.id).all()
        device_ids = [um.device_id for um in user_machines]
        devices = Device.query.filter(Device.id.in_(device_ids)).all()
    else:
        devices = []
    
    for d in devices:
        device_data = {
            "id": d.id,
            "name": d.name,
            "serial": d.serial,
            "status": d.status,
            "lat": d.lat,
            "lon": d.lon,
            "firmware": d.firmware,
            "config": d.config,
            "maxSpace": d.maxSpace,
            "freeSpace": d.freeSpace,
            "parameters": json.loads(d.parameters or '{}'),
            "displayParameters": json.loads(d.displayParameters or '[]'),
            "machine_model": d.machine_model,
            "machine_type": d.machine_type,
            "lastSync": d.last_sync.isoformat() if d.last_sync else None,
        }
        
        # Include log folders for admin users (needed for permission management)
        if current_user.role == 'admin':
            device_data["log_folders"] = [
                {"id": f.id, "name": f.name, "file_count": len(f.files), "files": [{"id": file.id, "name": file.name, "size": file.size, "modified": file.modified} for file in f.files]}
                for f in d.log_folders
            ]
        
        # For custom users, filter the visible data
        if current_user.role == 'custom':
            user_machine = UserMachine.query.filter_by(user_id=current_user.id, device_id=d.id).first()
            if user_machine:
                visible_fields = json.loads(user_machine.visible_data or '[]')
                # Filter parameters to only show visible fields
                filtered_params = {k: v for k, v in device_data["parameters"].items() if k in visible_fields}
                device_data["parameters"] = filtered_params
                # Filter displayParameters
                device_data["displayParameters"] = [p for p in device_data["displayParameters"] if p in visible_fields]
        
        result.append(device_data)
    
    return jsonify(result)

@app.route("/api/devices/<int:device_id>/logs")
@token_required
def get_log_folders(current_user, device_id):
    device = Device.query.get(device_id)
    if not device: return jsonify({"message": "Device not found"}), 404
    
    # Check permissions based on role
    if current_user.role == 'admin' or current_user.role == 'proto':
        # Admin and proto see all logs
        folders = [{'id': f.id, 'name': f.name, 'file_count': len(f.files)} for f in device.log_folders]
    elif current_user.role == 'production':
        # Production sees logs for assigned devices
        user_machine = UserMachine.query.filter_by(user_id=current_user.id, device_id=device_id).first()
        if not user_machine:
            return jsonify({"message": "Access denied"}), 403
        folders = [{'id': f.id, 'name': f.name, 'file_count': len(f.files)} for f in device.log_folders]
    elif current_user.role == 'custom':
        # Custom sees only allowed logs for assigned devices
        user_machine = UserMachine.query.filter_by(user_id=current_user.id, device_id=device_id).first()
        if not user_machine:
            return jsonify({"message": "Access denied"}), 403
        visible_logs = json.loads(user_machine.visible_logs or '[]')
        folders = []
        for f in device.log_folders:
            if f.id in visible_logs or f.name in visible_logs:
                folders.append({'id': f.id, 'name': f.name, 'file_count': len(f.files)})
    else:
        return jsonify({"message": "Access denied"}), 403
    
    return jsonify(folders)

@app.route("/api/logs/<int:folder_id>/files")
@token_required
def get_files_in_folder(current_user, folder_id):
    folder = LogFolder.query.get(folder_id)
    if not folder: return jsonify({"message": "Folder not found"}), 404
    
    device = folder.device
    
    # Check permissions based on role
    if current_user.role == 'admin' or current_user.role == 'proto':
        # Admin and proto see all files
        files = [{'id': f.id, 'name': f.name, 'size': f.size, 'modified': f.modified} for f in folder.files]
    elif current_user.role == 'production':
        # Production sees files for assigned devices
        user_machine = UserMachine.query.filter_by(user_id=current_user.id, device_id=device.id).first()
        if not user_machine:
            return jsonify({"message": "Access denied"}), 403
        files = [{'id': f.id, 'name': f.name, 'size': f.size, 'modified': f.modified} for f in folder.files]
    elif current_user.role == 'custom':
        # Custom sees only allowed files for assigned devices
        user_machine = UserMachine.query.filter_by(user_id=current_user.id, device_id=device.id).first()
        if not user_machine:
            return jsonify({"message": "Access denied"}), 403
        visible_logs = json.loads(user_machine.visible_logs or '[]')
        files = []
        for f in folder.files:
            if f.id in visible_logs or f.name in visible_logs or folder.id in visible_logs or folder.name in visible_logs:
                files.append({'id': f.id, 'name': f.name, 'size': f.size, 'modified': f.modified})
    else:
        return jsonify({"message": "Access denied"}), 403
    
    return jsonify(files)

if __name__ == "__main__":
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
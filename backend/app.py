from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
import werkzeug.exceptions  # <-- ADD THIS IMPORT
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
import json  # <-- ADD THIS IMPORT IF IT'S NOT THERE
import jwt
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask_socketio import SocketIO
from flask_migrate import Migrate
import os # <-- ADD THIS IMPORT
from flask import send_from_directory  # Add this for serving files from a directory

# --- ROBUST PATH CONFIGURATION ---
# Get the absolute path of the directory where this script is located (backend/)
basedir = os.path.abspath(os.path.dirname(__file__))
# Construct the absolute path to the static folder (one level up from backend/)
static_dir = os.path.join(os.path.dirname(basedir), 'static')

# Tell Flask to use this absolute path for the static folder.
app = Flask(__name__, static_folder=static_dir, static_url_path='/static')
# app = Flask(__name__)

CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")


# --- GLOBAL ERROR HANDLER ---
# This will catch any unhandled exception in the app and ensure a JSON response is sent.
@app.errorhandler(Exception)
def handle_exception(e):
    """Return JSON instead of HTML for any application-level error."""
    # Pass through HTTP-specific exceptions
    if isinstance(e, (werkzeug.exceptions.HTTPException,)):
        response = e.get_response()
        response.data = json.dumps({
            "code": e.code,
            "name": e.name,
            "message": e.description,
        })
        response.content_type = "application/json"
        return response

    # Handle non-HTTP exceptions with a generic 500 server error
    response = {
        "message": f"An internal server error occurred: {str(e)}",
        "code": 500,
        "name": "Internal Server Error"
    }
    return jsonify(response), 500



# --- CONFIGURATION ---
app.config['SECRET_KEY'] = 'your-super-secret-key-that-no-one-should-know'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'    # uncomment when you want tot use this internal
#app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://telematics_db_user:g5hivFFZWhCxkbAmOum07GoL2BMm1qPf@dpg-d44o0tkhg0os73fitedg-a/telematics_db'        # this used for render make it run on live

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'espdatalogger0@gmail.com' 
app.config['MAIL_PASSWORD'] = 'cndofvbtuxamnvom'

db = SQLAlchemy(app)
mail = Mail(app) # Initialize Mail
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
    last_sync = db.Column(db.DateTime)  # Add this field


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='user')
    is_active = db.Column(db.Boolean, default=False, nullable=False)
    full_name = db.Column(db.String(120))
    email = db.Column(db.String(120), unique=True, nullable=False)
    company = db.Column(db.String(120))
    dob = db.Column(db.String(50)) # Date of Birth
    birth_place = db.Column(db.String(120))
    mobile_number = db.Column(db.String(50))
    address = db.Column(db.String(255))
    reset_token = db.Column(db.String(100), unique=True)
    reset_token_expiration = db.Column(db.DateTime)
	
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


# --- DECORATORS (Security Guards) ---
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('x-access-token')
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = User.query.get(data['user_id'])
            # Add this check to handle cases where the user ID in the token no longer exists
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

# --- NEW: PROFILE & PASSWORD ENDPOINTS ---
@app.route("/api/profile", methods=['GET'])
@token_required
def get_profile(current_user):
    """Returns the current user's profile information."""
    return jsonify({
        'full_name': current_user.full_name, 'email': current_user.email,
        'company': current_user.company, 'dob': current_user.dob,
        'birth_place': current_user.birth_place, 'mobile_number': current_user.mobile_number,
        'address': current_user.address
    })

@app.route("/api/profile", methods=['PUT'])
@token_required
def update_profile(current_user):
    """Updates the current user's profile information."""
    data = request.get_json()
    try:
        # Update fields if they are provided in the request
        current_user.full_name = data.get('full_name', current_user.full_name)
        current_user.email = data.get('email', current_user.email)
        current_user.dob = data.get('dob', current_user.dob)
        current_user.birth_place = data.get('birth_place', current_user.birth_place)
        current_user.mobile_number = data.get('mobile_number', current_user.mobile_number)
        current_user.address = data.get('address', current_user.address)
        # This is the crucial line that saves the changes
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': f'An error occurred: {str(e)}'}), 500
    return jsonify({'message': 'Profile updated successfully!'})

@app.route("/api/change-password", methods=['POST'])
@token_required
def change_password(current_user):
    """Changes the current user's password."""
    data = request.get_json()
    if not data or 'current_password' not in data or 'new_password' not in data:
        return jsonify({'message': 'Current and new passwords are required.'}), 400
    if not check_password_hash(current_user.password_hash, data['current_password']):
        return jsonify({'message': 'Invalid current password.'}), 401
    current_user.password_hash = generate_password_hash(data['new_password'])
    db.session.commit()
    return jsonify({'message': 'Password changed successfully.'})

# Serve HTML files from the project root (adjust 'frontend' if your HTML is in a subfolder)
@app.route('/<path:filename>')
def serve_html(filename):
    # Assuming HTML files are in a 'frontend' folder relative to app.py (adjust path as needed)
    return send_from_directory('../', filename)  # '..' goes up to project root if backend/ is subfolder

# Or for root: Serve HomePage.html specifically
@app.route('/')
@app.route('/HomePage.html')
def home():
    return send_from_directory('../', 'HomePage.html')  # Adjust path if HTML is elsewhere


# --- AUTHENTICATION & ADMIN API ENDPOINTS ---
@app.route("/api/live-data", methods=['POST'])
def receive_live_data():
    data = request.get_json()
    if not data or 'device_id' not in data:
        return jsonify({"message": "Invalid data"}), 400
    
    print(f"Received data from device {data['device_id']}: {data}")
    
    # Emit a 'new_data' event to all connected browsers
    # We send it on a channel specific to the device_id
    socketio.emit(f'device_update_{data["device_id"]}', data)
    
    return jsonify({"message": "Data received"}), 200

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
    new_user = User(username=username, password_hash=hashed_password, full_name=full_name, email=email, company=data.get('company'))
    db.session.add(new_user)
    db.session.commit()
    return jsonify({"message": "Registration successful! Your account is pending admin approval."}), 201

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    user = User.query.filter_by(username=data.get('username')).first()
    if not user or not check_password_hash(user.password_hash, data.get('password')):
        return jsonify({"message": "Invalid credentials"}), 401
    if not user.is_active:
        return jsonify({"message": "Your account is pending approval by an administrator."}), 403
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

    # Generate a simple, secure, one-time use token
    reset_token = secrets.token_urlsafe(32)
    expiration = datetime.now(timezone.utc) + timedelta(minutes=15)
    
    # Save the token and its expiration to the user's record
    user.reset_token = reset_token
    user.reset_token_expiration = expiration
    db.session.commit()

    reset_url = f"http://127.0.0.1:5500/reset_password.html?token={reset_token}" 

    msg = Message('Password Reset Request', sender=app.config['MAIL_USERNAME'], recipients=[user.email])
    # Set the email body to an attractive HTML template with a hyperlink
    msg.html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; background-color: #f4f4f4; margin: 0; padding: 0; }}
            .container {{ width: 90%; max-width: 600px; margin: 20px auto; padding: 30px; border: 1px solid #ddd; border-radius: 8px; background-color: #ffffff; box-shadow: 0 4px 8px rgba(0,0,0,0.1); }}
            .header {{ font-size: 24px; font-weight: bold; text-align: center; margin-bottom: 20px; color: #0056b3; }}
            .button {{ display: inline-block; padding: 12px 25px; margin: 20px 0; font-size: 16px; font-weight: bold; color: #fff !important; background-color: #007bff; text-decoration: none; border-radius: 5px; text-align: center; }}
            .footer {{ font-size: 12px; color: #777; text-align: center; margin-top: 20px; }}
            p {{ margin-bottom: 15px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">Password Reset Request</div>
            <p>Hello {user.full_name},</p>
            <p>We received a request to reset the password for your account associated with this email address. To proceed, please click the button below:</p>
            <a href="{reset_url}" class="button">Reset Your Password</a>
            <p>This link is valid for 15 minutes. If you did not request a password reset, please ignore this email or contact support if you have concerns.</p>
            <div class="footer">
                <p>&copy; {datetime.now().year} ESP32 Data Logger. All rights reserved.</p>
            </div>
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

    # Find user by the one-time token and check if it has expired
    user = User.query.filter_by(reset_token=token).first()
    
    if not user or user.reset_token_expiration < datetime.now(timezone.utc):
        return jsonify({'message': 'Token is invalid or has expired. Please request a new one.'}), 401
    
    # Set the new password
    user.password_hash = generate_password_hash(new_password)
    # IMPORTANT: Invalidate the token by clearing it from the database
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
            'id': u.id, 'username': u.username, 'role': u.role, 'is_active': u.is_active, 
            'full_name': u.full_name, 'email': u.email, 'company': u.company,
            'dob': u.dob, 'birth_place': u.birth_place, 'mobile_number': u.mobile_number, 'address': u.address
        })
    return jsonify(output)

@app.route("/api/admin/approve/<int:user_id>", methods=['POST'])
@token_required
@admin_required
def approve_user(current_user, user_id):
    user = User.query.get(user_id)
    if not user: return jsonify({'message': 'User not found'}), 404
    user.is_active = True
    db.session.commit()
    return jsonify({'message': f'User {user.username} approved'})

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


# --- DATA API ENDPOINTS ---
@app.route("/api/devices")
@token_required
def get_devices(current_user):
    devices = Device.query.all()
    result = []
    for d in devices:
        result.append({
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
        })
    return jsonify(result)

@app.route("/api/devices/<int:device_id>/logs")
@token_required
def get_log_folders(current_user, device_id):
    device = Device.query.get(device_id)
    if not device: return jsonify({"message": "Device not found"}), 404
    folders = [{'id': f.id, 'name': f.name, 'file_count': len(f.files)} for f in device.log_folders]
    return jsonify(folders)

@app.route("/api/logs/<int:folder_id>/files")
@token_required
def get_files_in_folder(current_user, folder_id):
    folder = LogFolder.query.get(folder_id)
    if not folder: return jsonify({"message": "Folder not found"}), 404
    files = [{'id': f.id, 'name': f.name, 'size': f.size, 'modified': f.modified} for f in folder.files]
    return jsonify(files)

# --- MAIN EXECUTION ---

if __name__ == "__main__":
    socketio.run(app, debug=True)

# if __name__ == "__main__":
#     # Running without the reloader is more stable for Socket.IO
#     # The reloader can cause connection issues and empty responses.
#     print("Starting Flask-SocketIO server on http://127.0.0.1:5000")
#     # Added debug=True to enable the Werkzeug debugger for detailed error logs in the console.
#     socketio.run(app, host='127.0.0.1', port=5000, debug=True, use_reloader=False, allow_unsafe_werkzeug=True)
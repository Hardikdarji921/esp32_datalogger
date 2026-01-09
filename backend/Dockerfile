# Use a standard, small Python image
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt . 
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire rest of your web app (including your HTML/CSS/JS)
COPY . .

# Cloud Run requires your application to listen on the $PORT environment variable
# Gunicorn is used as a fast, production-ready web server
# NOTE: Replace 'your_app_file_name:app_object_name' with your actual setup.
# If your main file is 'website.py' and your Flask app object is 'server', use:
# CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 website:server
#
# If you used the previous guide's suggested structure (app.py and app = Flask(__name__)):
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 app:app
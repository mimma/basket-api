import os
from flask import Flask
from flask_jwt_extended import JWTManager

from config import Config
from api.models import db


app = Flask(__name__)
app.config.from_object(Config)

# Initialize extensions
db.init_app(app)
JWTManager(app)

# Create upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

from api import models
from api.ro
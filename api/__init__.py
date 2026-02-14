import os
from flask import Flask
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate

from config import Config
from api.models import db


app = Flask(__name__)
app.config.from_object(Config)

# Initialize extensions
db.init_app(app)
migrate = Migrate(app, db)
JWTManager(app)

# Create upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

from api import models
from api.routes import auth
from api.routes import video
from api.routes import user
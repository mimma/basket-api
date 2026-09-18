import os
from datetime import timedelta

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///basket.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # JWT Configuration
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or SECRET_KEY
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(days=30)

    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or 'uploads'
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB max file size
    ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov'}

    # suterska-ruka: YOLO model za detekciju igraca i lopte
    MODEL_PATH = os.environ.get('MODEL_PATH') or 'models/best.pt'

    # ffmpeg za prepakivanje rezultat-videa u H.264 (opciono; bez njega ostaje mp4v)
    FFMPEG_PATH = os.environ.get('FFMPEG_PATH') or 'ffmpeg'

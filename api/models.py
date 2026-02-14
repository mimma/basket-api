from datetime import datetime
from datetime import timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(255), unique=True, nullable=False, index=True)
    height = db.Column(db.Integer, nullable=False)
    unit = db.Column(db.String(10), nullable=False, default='cm')
    language = db.Column(db.String(10), nullable=False, default='sr')
    is_right_handed = db.Column(db.Boolean, nullable=False, default=True)
    terms_accepted = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    jobs = db.relationship('Job', backref='user', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'device_id': self.device_id,
            'height': self.height,
            'unit': self.unit,
            'language': self.language,
            'is_right_handed': self.is_right_handed,
            'terms_accepted': self.terms_accepted
        }


class Job(db.Model):
    __tablename__ = 'jobs'

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.String(255), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    front_video_path = db.Column(db.String(500))
    side_video_path = db.Column(db.String(500))
    result_video_url = db.Column(db.String(500))
    status = db.Column(db.String(50), nullable=False, default='uploaded')  # uploaded, processing, completed, failed
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False,
                           default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        result = {
            'id': self.id,
            'job_id': self.job_id,
            'status': self.status,
            'created_at': self.created_at.isoformat()
        }
        if self.result_video_url:
            result['video_url'] = self.result_video_url
        return result

import uuid

from flask import jsonify
from flask import request
from flask_jwt_extended import get_jwt_identity
from flask_jwt_extended import jwt_required

from api import app
from api import db
from api.constants import ERROR_BOTH_VIDEOS_REQUIRED
from api.constants import ERROR_EMPTY_FILENAME
from api.constants import ERROR_INVALID_VIDEO_EXTENSION
from api.constants import ERROR_JOB_CANNOT_BE_PROCESSED
from api.constants import ERROR_JOB_ID_REQUIRED
from api.constants import ERROR_JOB_NOT_FOUND
from api.constants import ERROR_USER_NOT_FOUND
from api.constants import STATUS_PROCESSING
from api.constants import STATUS_UPLOADED
from api.models import Job
from api.models import User
from api.storage import has_allowed_extension
from api.storage import save_job_videos


@app.route('/upload', methods=['POST'])
@jwt_required()
def upload_video():
    device_id = get_jwt_identity()
    user = User.query.filter_by(device_id=device_id).first()

    if not user:
        return jsonify({'error': ERROR_USER_NOT_FOUND}), 404

    # Check if files are present
    if 'front_video' not in request.files or 'side_video' not in request.files:
        return jsonify({'error': ERROR_BOTH_VIDEOS_REQUIRED}), 400

    front_video = request.files['front_video']
    side_video = request.files['side_video']

    if front_video.filename == '' or side_video.filename == '':
        return jsonify({'error': ERROR_EMPTY_FILENAME}), 400

    if not has_allowed_extension(front_video.filename) or not has_allowed_extension(side_video.filename):
        return jsonify({'error': ERROR_INVALID_VIDEO_EXTENSION}), 400

    # Generate unique job_id and save files to uploads/<device_id>/
    job_id = str(uuid.uuid4())
    front_path, side_path = save_job_videos(device_id, job_id, front_video, side_video)

    # Create job record with 'uploaded' status
    job = Job(job_id=job_id,
              user_id=user.id,
              front_video_path=front_path,
              side_video_path=side_path,
              status=STATUS_UPLOADED
              )

    db.session.add(job)
    db.session.commit()

    return jsonify({'id': job.id}), 201


@app.route('/process', methods=['POST'])
@jwt_required()
def process_video():
    device_id = get_jwt_identity()
    user = User.query.filter_by(device_id=device_id).first()

    if not user:
        return jsonify({'error': ERROR_USER_NOT_FOUND}), 404

    data = request.get_json()

    if not data or 'job_id' not in data:
        return jsonify({'error': ERROR_JOB_ID_REQUIRED}), 400

    job_id = data['job_id']
    job = Job.query.filter_by(id=job_id, user_id=user.id).first()

    if not job:
        return jsonify({'error': ERROR_JOB_NOT_FOUND}), 404

    if job.status != STATUS_UPLOADED:
        return jsonify({'error': ERROR_JOB_CANNOT_BE_PROCESSED.format(status=job.status)}), 400

    # Update status to processing
    job.status = STATUS_PROCESSING
    db.session.commit()

    # TODO: Trigger async video processing task here

    return jsonify({
        'job_id': job.job_id,
        'status': STATUS_PROCESSING
    }), 202


@app.route('/status/<job_id>', methods=['GET'])
@jwt_required()
def get_status(job_id):
    device_id = get_jwt_identity()
    user = User.query.filter_by(device_id=device_id).first()

    if not user:
        return jsonify({'error': ERROR_USER_NOT_FOUND}), 404

    job = Job.query.filter_by(job_id=job_id, user_id=user.id).first()

    if not job:
        return jsonify({'error': ERROR_JOB_NOT_FOUND}), 404

    return jsonify(job.to_dict()), 200

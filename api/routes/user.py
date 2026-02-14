import os

from flask import jsonify
from flask import request
from flask_jwt_extended import get_jwt_identity
from flask_jwt_extended import jwt_required

from api import app
from api import db
from api.constants import ERROR_JOB_NOT_FOUND
from api.constants import ERROR_USER_NOT_FOUND
from api.constants import SUCCESS_JOB_DELETED
from api.constants import SUCCESS_PROFILE_UPDATED
from api.models import Job
from api.models import User


@app.route('/profile', methods=['PUT'])
@jwt_required()
def update_profile():
    device_id = get_jwt_identity()
    user = User.query.filter_by(device_id=device_id).first()

    if not user:
        return jsonify({'error': ERROR_USER_NOT_FOUND}), 404

    data = request.get_json()

    # Update allowed fields
    if 'height' in data:
        user.height = data['height']
    if 'unit' in data:
        user.unit = data['unit']
    if 'language' in data:
        user.language = data['language']
    if 'is_right_handed' in data:
        user.is_right_handed = data['is_right_handed']

    db.session.commit()

    return jsonify({'message': SUCCESS_PROFILE_UPDATED, 'user_profile': user.to_dict()}), 200


@app.route('/history', methods=['GET'])
@jwt_required()
def get_history():
    device_id = get_jwt_identity()
    user = User.query.filter_by(device_id=device_id).first()

    if not user:
        return jsonify({'error': ERROR_USER_NOT_FOUND}), 404

    jobs = Job.query.filter_by(user_id=user.id).order_by(Job.created_at.desc()).all()

    return jsonify([job.to_dict() for job in jobs]), 200


@app.route('/history/<int:id>', methods=['DELETE'])
@jwt_required()
def delete_history(id):
    device_id = get_jwt_identity()
    user = User.query.filter_by(device_id=device_id).first()

    if not user:
        return jsonify({'error': ERROR_USER_NOT_FOUND}), 404

    job = Job.query.filter_by(id=id, user_id=user.id).first()

    if not job:
        return jsonify({'error': ERROR_JOB_NOT_FOUND}), 404

    # Delete video files
    if job.front_video_path and os.path.exists(job.front_video_path):
        os.remove(job.front_video_path)
    if job.side_video_path and os.path.exists(job.side_video_path):
        os.remove(job.side_video_path)
    # Note: result_video_url is external, not deleted here

    # Delete job record
    db.session.delete(job)
    db.session.commit()

    return jsonify({'message': SUCCESS_JOB_DELETED}), 200

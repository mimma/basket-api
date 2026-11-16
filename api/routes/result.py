from flask import jsonify
from flask import send_from_directory
from flask_jwt_extended import get_jwt_identity
from flask_jwt_extended import jwt_required

from api import app
from api.analysis import result_video_filename
from api.constants import ERROR_INVALID_CAMERA
from api.constants import ERROR_JOB_NOT_FOUND
from api.constants import ERROR_RESULT_VIDEO_NOT_FOUND
from api.constants import ERROR_USER_NOT_FOUND
from api.models import Job
from api.models import User
from api.storage import job_results_dir


@app.route('/result/<job_id>/<camera>/<int:shot_idx>', methods=['GET'])
@jwt_required()
def get_result_video(job_id, camera, shot_idx):
    """Vraca renderovani video jednog suta kao `video/mp4`.
    `job_id` je UUID, `camera` je `front` ili `side`, `shot_idx` redni broj suta."""
    device_id = get_jwt_identity()
    user = User.query.filter_by(device_id=device_id).first()

    if not user:
        return jsonify({'error': ERROR_USER_NOT_FOUND}), 404

    if camera not in ('front', 'side'):
        return jsonify({'error': ERROR_INVALID_CAMERA}), 400

    job = Job.query.filter_by(job_id=job_id, user_id=user.id).first()
    if not job:
        return jsonify({'error': ERROR_JOB_NOT_FOUND}), 404

    results_dir = job_results_dir(device_id, job_id).resolve()
    filename = result_video_filename(camera, shot_idx)
    if not (results_dir / filename).is_file():
        return jsonify({'error': ERROR_RESULT_VIDEO_NOT_FOUND}), 404

    return send_from_directory(results_dir, filename, mimetype='video/mp4',
                               conditional=True,
                               download_name=f"{job_id}_{filename}")

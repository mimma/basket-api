import uuid

from flask import current_app
from flask import jsonify
from flask import request
from flask import send_from_directory
from flask_jwt_extended import get_jwt_identity
from flask_jwt_extended import jwt_required

from api import app
from api import db
from api.analysis import analysis_failed
from api.analysis import analyze_front_and_side
from api.analysis import result_video_filename
from api.constants import ERROR_ANALYSIS_FAILED
from api.constants import ERROR_BOTH_VIDEOS_REQUIRED
from api.constants import ERROR_EMPTY_FILENAME
from api.constants import ERROR_INVALID_CAMERA
from api.constants import ERROR_INVALID_VIDEO_EXTENSION
from api.constants import ERROR_JOB_NOT_FOUND
from api.constants import ERROR_RESULT_VIDEO_NOT_FOUND
from api.constants import ERROR_USER_NOT_FOUND
from api.constants import STATUS_COMPLETED
from api.constants import STATUS_FAILED
from api.constants import STATUS_PROCESSING
from api.models import Job
from api.models import User
from api.storage import has_allowed_extension
from api.storage import job_results_dir
from api.storage import save_job_videos


@app.route('/analyze', methods=['POST'])
@jwt_required()
def analyze_videos():
    """Prima `front_video` i `side_video` (multipart/form-data), snima ih,
    pusta suterska-ruka analizu nad oba snimka i vraca rezultat po kameri.
    Za svaki uspesno analizirani sut renderuje video, dostupan na
    GET /result/<job_id>/<camera>/<shot_idx> (`video_url` u rezultatu); JSON
    izvestaj za crtanje je u `video_report` istog suta.

    Analiza se izvrsava sinhrono u okviru zahteva, pa odgovor moze potrajati
    vise desetina sekundi po snimku (CPU inference)."""
    device_id = get_jwt_identity()
    user = User.query.filter_by(device_id=device_id).first()

    if not user:
        return jsonify({'error': ERROR_USER_NOT_FOUND}), 404

    if 'front_video' not in request.files or 'side_video' not in request.files:
        return jsonify({'error': ERROR_BOTH_VIDEOS_REQUIRED}), 400

    front_video = request.files['front_video']
    side_video = request.files['side_video']

    if front_video.filename == '' or side_video.filename == '':
        return jsonify({'error': ERROR_EMPTY_FILENAME}), 400

    if not has_allowed_extension(front_video.filename) or not has_allowed_extension(side_video.filename):
        return jsonify({'error': ERROR_INVALID_VIDEO_EXTENSION}), 400

    job_id = str(uuid.uuid4())
    front_path, side_path = save_job_videos(device_id, job_id, front_video, side_video)

    job = Job(job_id=job_id,
              user_id=user.id,
              front_video_path=front_path,
              side_video_path=side_path,
              status=STATUS_PROCESSING
              )
    db.session.add(job)
    db.session.commit()

    shooting_hand = 'right' if user.is_right_handed else 'left'

    try:
        analysis = analyze_front_and_side(front_path, side_path, shooting_hand,
                                          job_id, job_results_dir(device_id, job_id))
    except Exception:
        current_app.logger.exception("Analysis crashed for job %s", job_id)
        job.status = STATUS_FAILED
        db.session.commit()
        return jsonify({'id': job.id, 'job_id': job.job_id, 'status': job.status,
                        'error': ERROR_ANALYSIS_FAILED}), 500

    # Biblioteka ne dize exception za los video, vec vraca status `failed_*` po kameri.
    failed = analysis_failed(analysis['front']) or analysis_failed(analysis['side'])
    job.status = STATUS_FAILED if failed else STATUS_COMPLETED
    job.set_analysis(analysis)
    db.session.commit()

    return jsonify({
        'id': job.id,
        'job_id': job.job_id,
        'status': job.status,
        'shooting_hand': shooting_hand,
        'result': analysis,
        'videos': Job.result_videos(analysis)
    }), 422 if failed else 200


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

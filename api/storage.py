import os
import shutil
from pathlib import Path

from flask import current_app
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


def has_allowed_extension(filename: str) -> bool:
    if '.' not in filename:
        return False
    extension = filename.rsplit('.', 1)[1].lower()
    return extension in current_app.config['ALLOWED_VIDEO_EXTENSIONS']


def save_job_videos(device_id: str, job_id: str,
                    front_video: FileStorage, side_video: FileStorage) -> tuple[str, str]:
    """Snima front i side video u uploads/<device_id>/ i vraca njihove putanje."""
    user_folder = Path(current_app.config['UPLOAD_FOLDER']) / device_id
    user_folder.mkdir(parents=True, exist_ok=True)

    front_filename = secure_filename(f"{job_id}_front_{front_video.filename}")
    side_filename = secure_filename(f"{job_id}_side_{side_video.filename}")

    front_path = str(user_folder / front_filename)
    side_path = str(user_folder / side_filename)

    front_video.save(front_path)
    side_video.save(side_path)

    return front_path, side_path


def job_results_dir(device_id: str, job_id: str) -> Path:
    """Folder sa renderovanim rezultat-videima: uploads/<device_id>/results/<job_id>/."""
    return Path(current_app.config['UPLOAD_FOLDER']) / device_id / 'results' / job_id


def delete_job_files(job) -> None:
    """Brise front/side snimke i folder sa rezultat-videima jednog joba."""
    for path in (job.front_video_path, job.side_video_path):
        if path and os.path.exists(path):
            os.remove(path)
    results_dir = job_results_dir(job.user.device_id, job.job_id)
    if results_dir.is_dir():
        shutil.rmtree(results_dir, ignore_errors=True)

"""Integracija suterska-ruka biblioteke: jedan model po procesu.

Pored JSON rezultata, za svaki uspesno analizirani sut renderuje se video
(isecak suta sa linijama skeleta, usporenjem i pauzama na greskama). Biblioteka
vise ne crta greske u video; njen JSON izvestaj (izlaz `save_result_video`) vraca
se po sutu kao `video_report` i iz njega frontend uzima sve za crtanje (frejmovi i
sekunde u njemu odnose se na renderovani video)."""
import logging
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

import cv2
import json
from flask import current_app
from suterska_ruka.analyze_video import AnalyzeStages
from suterska_ruka.analyze_video import VideoAnalysisError
from suterska_ruka.analyzer import DEFAULT_INFERENCE_PARAMETERS
from suterska_ruka.analyzer import _build_shot
from suterska_ruka.write_video import save_result_video

from api.constants import STATUS_COMPLETED
from api.constants import STATUS_FAILED
from api.models import Job
from api.models import db
from api.storage import job_results_dir

logger = logging.getLogger(__name__)

_stages: AnalyzeStages | None = None
# AnalyzeStages nije thread-safe, pa se u okviru jednog procesa ucitavanje modela,
# analiza i renderovanje serijalizuju kroz jedan lock. Server svaku analizu
# ionako pusta u zaseban proces (api/worker.py).
_lock = threading.Lock()


def _get_stages() -> AnalyzeStages:
    # Isto sto radi ShotAnalyzer.__init__, ali nam trebaju DataClass objekti
    # (a ne samo dict koji ShotAnalyzer.analyze vraca) da bismo iscrtali video.
    global _stages
    if _stages is None:
        model_path = current_app.config['MODEL_PATH']
        logger.info("Loading suterska-ruka model from %s", model_path)
        _stages = AnalyzeStages(model_path, recompute=True,
                                infer_parameters=dict(DEFAULT_INFERENCE_PARAMETERS),
                                save_intermediate=False)
    return _stages


def analysis_failed(result: dict) -> bool:
    """Biblioteka ne dize exception vec vraca top-level `status: failed_*`."""
    return str(result.get('status', '')).startswith('failed_')


def result_video_filename(camera: str, shot_idx: int) -> str:
    return f"{camera}_{shot_idx}.mp4"


def _source_rotation(ffmpeg: str, video_path: str) -> int:
    """Rotacija iz metapodataka snimka (telefoni snimaju 1280x720 + rotate), u stepenima
    kako je ffprobe prijavljuje (pozitivno = u smeru suprotnom od kazaljke)."""
    ffprobe = shutil.which(str(Path(ffmpeg).with_name('ffprobe'))) or shutil.which('ffprobe')
    if ffprobe is None:
        return 0
    cmd = [ffprobe, '-v', 'error', '-select_streams', 'v:0', '-show_streams',
           '-of', 'json', video_path]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return 0
    try:
        stream = json.loads(proc.stdout)['streams'][0]
    except (ValueError, KeyError, IndexError):
        return 0
    for side_data in stream.get('side_data_list', []):
        if 'rotation' in side_data:
            return int(round(float(side_data['rotation']))) % 360
    # stariji zapis: tag `rotate` je u smeru kazaljke
    rotate = stream.get('tags', {}).get('rotate')
    return (-int(rotate)) % 360 if rotate else 0


def normalize_rotation(video_path: str) -> None:
    """Fizicki okrece snimak prema njegovim rotate metapodacima i prepisuje ga na istom mestu.

    OpenCV, kroz koji biblioteka cita frejmove, tu rotaciju ignorise: poza bi se
    trazila na polozenom igracu, a renderovani video
    (skelet) bio bi polozen. Bez ffmpeg-a snimak ostaje kakav jeste."""
    ffmpeg = shutil.which(current_app.config['FFMPEG_PATH'])
    if ffmpeg is None:
        return
    rotation = _source_rotation(ffmpeg, video_path)
    if rotation == 0:
        return

    src = Path(video_path)
    tmp = src.with_name(f"{src.stem}.rotating{src.suffix}")
    # ffmpeg pri re-enkodiranju sam primenjuje display matrix (autorotate) i ne prenosi ga dalje
    cmd = [ffmpeg, '-y', '-loglevel', 'error', '-i', str(src),
           '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p',
           '-c:a', 'copy', '-movflags', '+faststart', str(tmp)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        logger.warning("Rotation normalize failed for %s (%s); analyzing as-is",
                       src.name, proc.stderr.strip())
        tmp.unlink(missing_ok=True)
        return
    tmp.replace(src)
    logger.info("Normalized rotation of %s by %s degrees", src.name, rotation)


def _transcode_to_h264(src: Path, dst: Path) -> None:
    """OpenCV pise `mp4v` (MPEG-4 Part 2) koji browseri i telefoni cesto ne pustaju,
    pa se video prepakuje u H.264 ako je ffmpeg dostupan; inace se kopira kakav jeste."""
    ffmpeg = shutil.which(current_app.config['FFMPEG_PATH'])
    if ffmpeg is None:
        logger.warning("ffmpeg not found; result video %s left as mp4v", dst.name)
        shutil.copyfile(src, dst)
        return

    cmd = [ffmpeg, '-y', '-loglevel', 'error', '-i', str(src),
           '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
           # libx264 + yuv420p traze parne dimenzije
           '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',
           '-an', str(dst)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        logger.warning("ffmpeg failed for %s (%s); falling back to mp4v", dst.name, proc.stderr.strip())
        shutil.copyfile(src, dst)


def _render_shot_video(data_class, video_path: str, camera: str, shot_idx: int,
                       shooting_hand: str, results_dir: Path, video_url: str) -> dict | None:
    """Renderuje video jednog suta u results_dir/<camera>_<shot_idx>.mp4 i vraca
    JSON izvestaj biblioteke za taj video, sa `video_url` (None ako renderovanje
    nije uspelo)."""
    cap = cv2.VideoCapture(video_path)
    try:
        with tempfile.TemporaryDirectory(prefix='basket-render-') as tmp:
            report = save_result_video(data_class, camera, cap, save_path=tmp,
                                       shooting_hand=shooting_hand)
            rendered = list(Path(tmp).glob('*.mp4'))
            if len(rendered) != 1:
                raise ValueError(f"Expected one rendered video, found {len(rendered)}")
            results_dir.mkdir(parents=True, exist_ok=True)
            dst = results_dir / result_video_filename(camera, shot_idx)
            _transcode_to_h264(rendered[0], dst)
            return _public_report(report, video_url)
    except (ValueError, OSError, cv2.error):
        logger.exception("Failed to render result video for %s shot %s", camera, shot_idx)
        (results_dir / result_video_filename(camera, shot_idx)).unlink(missing_ok=True)
        return None
    finally:
        cap.release()


# Polja izvestaja koja opisuju privremene/interne fajlove na serveru.
_INTERNAL_REPORT_KEYS = ('video', 'video_path', 'source_video')


def _public_report(report: dict, video_url: str) -> dict:
    """Izvestaj za klijenta: bez internih putanja, a sa `video_url` (GET /result/...)
    videa na koji se svi frejmovi i sekunde izvestaja odnose."""
    public = {'video_url': video_url}
    public.update((k, v) for k, v in report.items() if k not in _INTERNAL_REPORT_KEYS)
    return public


def _analyze_camera(video_path: str, camera: str, shooting_hand: str,
                    job_id: str, results_dir: Path) -> dict:
    """Ekvivalent ShotAnalyzer.analyze(), prosiren renderovanjem videa po sutu."""
    normalize_rotation(video_path)
    stages = _get_stages()
    try:
        data_classes = stages.analyze_video(video_path, camera, shooting_hand)
    except VideoAnalysisError as e:
        return {'camera': camera, 'shooting_hand': shooting_hand,
                'status': f"failed_{e.stage}", 'error': str(e), 'shots': []}

    shots = []
    for shot_idx, data_class in enumerate(data_classes):
        # _build_shot pokrece detekciju gresaka i upisuje ih u data_class,
        # sto je preduslov za save_result_video.
        shot = _build_shot(shot_idx, data_class, camera, shooting_hand)
        if shot['status'] == 'ok':
            video_url = f"/result/{job_id}/{camera}/{shot_idx}"
            report = _render_shot_video(data_class, video_path, camera, shot_idx,
                                        shooting_hand, results_dir, video_url)
            shot['video_url'] = None if report is None else video_url
            shot['video_report'] = report
        shots.append(shot)

    return {'camera': camera, 'shooting_hand': shooting_hand, 'shots': shots}


def analyze_front_and_side(front_path: str, side_path: str, shooting_hand: str,
                           job_id: str, results_dir: Path) -> dict:
    """Analizira par snimaka (front + side), renderuje video po sutu u results_dir
    i vraca JSON-serializable dict po kameri (sa `video_url` i `video_report` po
uspesnom sutu)."""
    with _lock:
        front_result = _analyze_camera(front_path, 'front', shooting_hand, job_id, results_dir)
        side_result = _analyze_camera(side_path, 'side', shooting_hand, job_id, results_dir)

    return {'front': front_result, 'side': side_result}


def run_job_analysis(job: Job, shooting_hand: str) -> dict:
    """Analizira snimke joba, upisuje rezultat i status (`completed`/`failed`) u bazu
    i vraca analizu. Exception iz analize se propagira (status ostaje nepromenjen)."""
    results_dir = job_results_dir(job.user.device_id, job.job_id)
    # Videi prethodnog (prekinutog) pokusaja ne smeju da ostanu dostupni preko /result.
    shutil.rmtree(results_dir, ignore_errors=True)
    analysis = analyze_front_and_side(job.front_video_path, job.side_video_path, shooting_hand,
                                      job.job_id, results_dir)
    # Biblioteka ne dize exception za los video, vec vraca status `failed_*` po kameri.
    failed = analysis_failed(analysis['front']) or analysis_failed(analysis['side'])
    job.status = STATUS_FAILED if failed else STATUS_COMPLETED
    job.set_analysis(analysis)
    db.session.commit()
    return analysis


def shooting_hand_of(user) -> str:
    return 'right' if user.is_right_handed else 'left'

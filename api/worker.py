"""Pozadinska analiza jobova, svaka u zasebnom procesu.

POST /process stavlja job u red; dispecer niti u server procesu (najvise
ANALYSIS_WORKERS istovremeno) za svaki job pokrecu novi proces koji ucita model,
analizira snimke i upise rezultat u bazu. Niti samo cekaju na proces, pa GIL ne
smeta, a pad procesa (segfault, OOM u mediapipe/torch) ne obara server. Posle
svakog joba proces se gasi i oslobadja memoriju modela.

Job koji je pao (proces umro, ili server ugasen usred analize) pokusava se ponovo,
najvise MAX_ATTEMPTS puta ukupno, pa se oznacava kao `failed`.

Red je u memoriji jednog server procesa; za vise server procesa ili masina treba
pravi red poslova (RQ/Celery)."""
import logging
import multiprocessing
import queue
import threading

from flask import Flask

from api.analysis import run_job_analysis
from api.analysis import shooting_hand_of
from api.constants import STATUS_FAILED
from api.constants import STATUS_PROCESSING
from api.models import Job
from api.models import db

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 2

# spawn umesto fork: server proces ima niti (Flask, dispeceri), a fork procesa sa
# nitima i vec ucitanim torch-om nije bezbedan.
_mp = multiprocessing.get_context('spawn')

_queue: queue.Queue[int] = queue.Queue()
# Jobovi koji su u redu ili se upravo analiziraju, da se isti job ne pokrene dvaput.
_pending: set[int] = set()
_state_lock = threading.Lock()
_dispatchers_started = False
_resumed = False


def enqueue_job(app: Flask, job_pk: int) -> None:
    """Stavlja job (u statusu `processing`) u red za analizu."""
    _start_dispatchers(app)
    with _state_lock:
        if job_pk in _pending:
            return
        _pending.add(job_pk)
    _queue.put(job_pk)


def resume_interrupted_jobs(app: Flask) -> None:
    """Vraca u red jobove zatecene u `processing` (server je ugasen tokom analize).

    Poziva se na prvom zahtevu (ne pri importu, da je ne bi pokrenuo Flask reloader
    roditeljski proces ili skripte koje uvoze `api`). Greska se samo loguje i
    pokusava ponovo na sledecem zahtevu; zahtev klijenta zbog nje ne pada."""
    global _resumed
    if _resumed:
        return
    with _state_lock:
        if _resumed:
            return
        try:
            job_pks = [pk for (pk,) in db.session.query(Job.id)
                       .filter(Job.status == STATUS_PROCESSING).all()]
        except Exception:
            logger.exception("Could not look up interrupted jobs; will retry on next request")
            db.session.rollback()
            return
        _resumed = True
    for job_pk in job_pks:
        logger.warning("Resuming interrupted analysis of job pk=%s", job_pk)
        enqueue_job(app, job_pk)


def _start_dispatchers(app: Flask) -> None:
    global _dispatchers_started
    with _state_lock:
        if _dispatchers_started:
            return
        _dispatchers_started = True
        workers = max(1, int(app.config['ANALYSIS_WORKERS']))
    for i in range(workers):
        threading.Thread(target=_dispatch_loop, args=(app,), daemon=True,
                         name=f"analysis-dispatcher-{i}").start()


def _dispatch_loop(app: Flask) -> None:
    while True:
        job_pk = _queue.get()
        retry = False
        try:
            retry = _run_job(app, job_pk)
        except Exception:
            logger.exception("Dispatcher failed for job pk=%s", job_pk)
        finally:
            with _state_lock:
                _pending.discard(job_pk)
        if retry:
            enqueue_job(app, job_pk)


def _run_job(app: Flask, job_pk: int) -> bool:
    """Pokrece analizu joba u zasebnom procesu i ceka ga. Vraca True ako je proces
    umro pre nego sto je upisao rezultat, pa job treba pokusati ponovo."""
    with app.app_context():
        job = db.session.get(Job, job_pk)
        if job is None or job.status != STATUS_PROCESSING:
            return False
        if job.attempts >= MAX_ATTEMPTS:
            logger.error("Job %s failed %s times; marking as failed", job.job_id, job.attempts)
            job.status = STATUS_FAILED
            db.session.commit()
            return False
        job.attempts += 1
        db.session.commit()
        job_id = job.job_id

    proc = _mp.Process(target=_analyze_in_process, args=(job_pk,), name=f"analysis-{job_id}")
    proc.start()
    proc.join()
    if proc.exitcode == 0:
        return False
    logger.error("Analysis process for job %s died (exit code %s)", job_id, proc.exitcode)
    return True


def _analyze_in_process(job_pk: int) -> None:
    """Ulazna tacka procesa za analizu (novi interpreter, zbog spawn-a)."""
    from api import app

    with app.app_context():
        job = db.session.get(Job, job_pk)
        try:
            run_job_analysis(job, shooting_hand_of(job.user))
        except Exception:
            logger.exception("Analysis crashed for job %s", job.job_id)
            db.session.rollback()
            job.status = STATUS_FAILED
            db.session.commit()

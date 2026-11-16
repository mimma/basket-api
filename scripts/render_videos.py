"""Batch: analizira sve snimke iz foldera (videos/front/*.mp4, videos/side/*.mp4)
i renderuje po sutu video + JSON izvestaj za crtanje, bez API-ja i baze.

    python scripts/render_videos.py                       # videos/ -> result_videos/
    python scripts/render_videos.py -i videos -o out --shooting-hand left

Kamera se odredjuje iz imena podfoldera (`front`/`side`) ili prefiksa fajla.
Originali se ne menjaju: snimak se kopira u privremeni folder pre normalizacije rotacije."""
import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api import app  # noqa: E402
from api.analysis import _analyze_camera  # noqa: E402
from api.analysis import _lock  # noqa: E402
from api.analysis import result_video_filename  # noqa: E402

VIDEO_SUFFIXES = {'.mp4', '.mov', '.avi'}


def camera_for(path: Path) -> str | None:
    for candidate in (path.parent.name.lower(), path.stem.lower().split('_')[0]):
        if candidate in ('front', 'side'):
            return candidate
    return None


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('-i', '--input', type=Path, default=Path('videos'))
    p.add_argument('-o', '--output', type=Path, default=Path('result_videos'))
    p.add_argument('--shooting-hand', choices=['right', 'left'], default='right')
    args = p.parse_args()

    videos = sorted(f for f in args.input.rglob('*') if f.suffix.lower() in VIDEO_SUFFIXES)
    if not videos:
        print(f"Nema snimaka u {args.input}", file=sys.stderr)
        return 1

    args.output.mkdir(parents=True, exist_ok=True)
    summary = []
    with app.app_context(), tempfile.TemporaryDirectory(prefix='basket-batch-') as tmp:
        for video in videos:
            camera = camera_for(video)
            if camera is None:
                print(f"SKIP {video}: ne mogu da odredim kameru (front/side)")
                continue
            work_copy = Path(tmp) / video.name
            shutil.copyfile(video, work_copy)
            shot_dir = Path(tmp) / f"{video.stem}_out"

            print(f"{video} [{camera}] ...", flush=True)
            with _lock:
                result = _analyze_camera(str(work_copy), camera, args.shooting_hand,
                                         video.stem, shot_dir)

            rendered = []
            for shot in result['shots']:
                src = shot_dir / result_video_filename(camera, shot['shot_idx'])
                if shot.get('video_url') and src.is_file():
                    dst = args.output / f"{video.stem}_shot{shot['shot_idx']}.mp4"
                    shutil.move(src, dst)
                    rendered.append(str(dst))
                    # JSON izvestaj za crtanje, pored videa i sa njegovim imenom
                    report = dict(shot['video_report'])
                    report.pop('video_url', None)
                    report = {'video': dst.name, **report}
                    dst.with_suffix('.json').write_text(
                        json.dumps(report, indent=2, ensure_ascii=False))
                shot.pop('video_url', None)
            result['file'] = str(video)
            result['rendered'] = rendered
            summary.append(result)

            status = result.get('status', 'ok')
            print(f"  -> {status}, sutova: {len(result['shots'])}, videa: {len(rendered)}"
                  + (f" ({result['error']})" if 'error' in result else ''))

    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nGotovo. Rezultati u {args.output}/ (summary.json + mp4 i json po sutu)")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

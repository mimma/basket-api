# Basket API

Flask API projekat za obradu video snimaka.

## Instalacija

> **Python 3.12 je obavezan.** Analiza šuta koristi biblioteku
> [suterska-ruka](https://github.com/mimma/suterska-ruka), koja radi nad
> `mediapipe==0.10.21` (legacy `mediapipe.solutions` API). Ta verzija ne
> postoji za Python 3.13+.

1. Kreirajte virtuelno okruženje:
```bash
python3.12 -m venv venv
source venv/bin/activate  # Linux/Mac
# ili
venv\Scripts\activate  # Windows
```

2. Instalirajte zavisnosti (biblioteka ide posebno, bez rezolucije njenih zavisnosti,
   jer njen `opencv-python>=4.12` pin nije kompatibilan sa `numpy<2` koji traži mediapipe):
```bash
# opciono, za mašine bez NVIDIA GPU-a (znatno manji venv):
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

pip install -r requirements.txt
pip install --no-deps "suterska-ruka @ git+ssh://git@github.com/mimma/suterska-ruka.git@main"
```

3. Postavite YOLO model na `models/best.pt` (ili zadajte putanju preko `MODEL_PATH`).

4. Kreirajte `.env` fajl (kopirajte `.env.example`):
```bash
cp .env.example .env
```

5. Primenite migracije baze:
```bash
flask --app app.py db upgrade
```

## Pokretanje

```bash
python app.py
```

API će biti dostupan na `http://localhost:5000`

## Endpoints

### 1. POST /login
- Registracija (prvi put): `{"device_id": "XY", "height": 185, "unit": "cm", "language": "sr", "is_right_handed": true, "terms_accepted": true}`
- Login (svaki sledeći put): `{"device_id": "XY"}`

### 2. PUT /profile
Header: `Authorization: Bearer <token>`
Body: `{"height": 182, "language": "en"}`

### 3. POST /upload
Header: `Authorization: Bearer <token>`
Type: `multipart/form-data`
Files: `front_video`, `side_video`

### 4. POST /analyze
Header: `Authorization: Bearer <token>`
Type: `multipart/form-data`
Files: `front_video` (snimak spreda), `side_video` (snimak sa strane); dozvoljeno `mp4`, `avi`, `mov`

Snima oba videa, kreira job i **sinhrono** pušta `suterska-ruka` analizu nad oba
(ruka kojom igrač šutira uzima se iz profila, `is_right_handed`). Snimci sa telefona
koji nose `rotate` metapodatke se pre analize fizički okrenu (ffmpeg) i prepišu na
istom mestu, jer OpenCV tu rotaciju ignoriše. Za svaki uspešno
analizirani šut renderuje se i anotirani video (skelet, lopta, faza šuta, istaknute
greške) u `uploads/<device_id>/results/<job_id>/<camera>_<shot_idx>.mp4`. Video se
prepakuje u H.264 preko `ffmpeg`-a (`FFMPEG_PATH`, podrazumevano `ffmpeg` sa PATH-a);
bez ffmpeg-a ostaje OpenCV `mp4v` koji browseri i telefoni često ne puštaju.
Odgovor može potrajati više desetina sekundi po snimku na CPU-u, plus renderovanje.

Response (200 OK, ili 422 ako biblioteka nije uspela da obradi neki od snimaka):
```json
{
  "id": 7,
  "job_id": "e1b4...",
  "status": "completed",
  "shooting_hand": "right",
  "result": {
    "front": {"camera": "front", "shooting_hand": "right", "shots": [ {"shot_idx": 0, "status": "ok", "phases": {...}, "errors_per_frame": {...}, "error_label_counts": {...}, "video_url": "/result/e1b4.../front/0"} ]},
    "side":  {"camera": "side",  "shooting_hand": "right", "shots": [ ... ]}
  },
  "videos": [
    {"camera": "front", "shot_idx": 0, "url": "/result/e1b4.../front/0"},
    {"camera": "side",  "shot_idx": 0, "url": "/result/e1b4.../side/0"}
  ]
}
```
Rezultat se čuva u `jobs.analysis_result` i vraća se i kroz `GET /status/{job_id}` i `GET /history` (polja `analysis` i `videos`).

### 5. GET /result/{job_id}/{camera}/{shot_idx}
Header: `Authorization: Bearer <token>`

Vraća renderovani video jednog šuta kao `video/mp4` (`camera` je `front` ili `side`,
`shot_idx` redni broj šuta iz rezultata). URL-ovi se dobijaju iz `videos` / `video_url`.
U Postman-u koristiti "Send and Download" da bi se fajl sačuvao; u browseru ili
plejeru može direktno da se pusti (`ffmpeg` H.264 varijanta).

`DELETE /history/{id}` briše i ove fajlove.

### 6. GET /status/{job_id}
Header: `Authorization: Bearer <token>`

### 7. GET /history
Header: `Authorization: Bearer <token>`

### 8. DELETE /history/{id}
Header: `Authorization: Bearer <token>`

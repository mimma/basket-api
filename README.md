# Basket API

Flask REST API za analizu tehnike košarkaškog šuta. Klijent (mobilna aplikacija)
šalje dva snimka istog šuta, spreda (`front`) i sa strane (`side`), a API vraća:

- **JSON rezultat analize**: faze šuta (početak, set point, izbačaj, skok), greške u
  tehnici po frejmu i zbirno po šutu;
- **anotirani video** po šutu: originalni kadar sa iscrtanim skeletom, loptom,
  fazom šuta i istaknutim greškama.

Samu analizu radi biblioteka [suterska-ruka](https://github.com/mimma/suterska-ruka)
(YOLO za igrača i loptu, MediaPipe za pozu). API je omotač oko nje: autentikacija po
uređaju, skladištenje snimaka, baza jobova, isporuka videa.

## Sadržaj

1. [Zahtevi](#zahtevi)
2. [Instalacija](#instalacija)
3. [Konfiguracija](#konfiguracija)
4. [Baza i migracije](#baza-i-migracije)
5. [Pokretanje](#pokretanje)
6. [Brzi test sa curl-om](#brzi-test-sa-curl-om)
7. [Postman kolekcija](#postman-kolekcija)
8. [Endpointi](#endpointi)
9. [Format rezultata analize](#format-rezultata-analize)
10. [Batch renderovanje bez API-ja](#batch-renderovanje-bez-api-ja)
11. [Kako radi obrada videa](#kako-radi-obrada-videa)
12. [Struktura projekta](#struktura-projekta)
13. [Česti problemi](#česti-problemi)

## Zahtevi

| Šta | Verzija / napomena |
|---|---|
| Python | **tačno 3.12**. `mediapipe==0.10.21` (poslednja verzija sa legacy `mediapipe.solutions` API-jem koji biblioteka koristi) ne postoji za 3.13+. |
| ffmpeg + ffprobe | Preporučeno. Koristi se za ispravljanje rotacije snimaka sa telefona i za prepakivanje izlaznog videa u H.264. Bez njega sve radi, ali video ostaje u `mp4v` kodeku koji browseri i telefoni često ne puštaju, a položeni snimci ostaju položeni. |
| YOLO model | `models/best.pt` (težine za detekciju igrača i lopte), nije u repozitorijumu. |
| Pristup GitHub repou `mimma/suterska-ruka` | Biblioteka se instalira preko `git+ssh`, potreban je SSH ključ. |
| GPU | Nije obavezan. Na CPU-u analiza traje oko 40 s po snimku od 30 s; kratak klip od 3 s obradi se za nekoliko sekundi. |

Instalacija ffmpeg-a:

```bash
sudo pacman -S ffmpeg          # Arch
sudo apt install ffmpeg        # Debian/Ubuntu
brew install ffmpeg            # macOS
```

## Instalacija

```bash
git clone <url-ovog-repoa> basket-api
cd basket-api

# 1. Virtuelno okruženje (obavezno Python 3.12)
python3.12 -m venv venv
source venv/bin/activate          # Linux/macOS
# venv\Scripts\activate           # Windows

# 2. (opciono) torch bez CUDA-e, znatno manji venv za mašine bez NVIDIA GPU-a
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

# 3. Zavisnosti API-ja i pinovane verzije za biblioteku
pip install -r requirements.txt

# 4. Sama biblioteka, bez rezolucije njenih zavisnosti
pip install --no-deps "suterska-ruka @ git+ssh://git@github.com/mimma/suterska-ruka.git@main"

# 5. YOLO model
mkdir -p models
cp /putanja/do/best.pt models/best.pt

# 6. Konfiguracija
cp .env.example .env

# 7. Baza
flask --app app.py db upgrade
```

Zašto `--no-deps` u koraku 4: biblioteka pinuje `opencv-python>=4.12`, a mediapipe
0.10.21 traži `numpy<2` koji opencv podržava samo do 4.11.x. Zato `requirements.txt`
sam pinuje `mediapipe`, `numpy`, `opencv-python` i `ultralytics`, a biblioteka se
instalira preko njih bez proveravanja sopstvenih pinova.

Provera da je sve na mestu:

```bash
source venv/bin/activate
python -c "import mediapipe, cv2, ultralytics, suterska_ruka; print('ok')"
ffmpeg -version | head -1
ls -la models/best.pt
```

Ažuriranje biblioteke na najnoviji `main`:

```bash
pip install --no-deps --force-reinstall --no-cache-dir \
  "suterska-ruka @ git+ssh://git@github.com/mimma/suterska-ruka.git@main"
```

## Konfiguracija

Podešavanja se čitaju iz `.env` (preko `python-dotenv`) i `config.py`.

| Promenljiva | Podrazumevano | Opis |
|---|---|---|
| `SECRET_KEY` | `dev-secret-key-change-in-production` | Flask tajni ključ. **Obavezno promeniti u produkciji.** |
| `JWT_SECRET_KEY` | isto kao `SECRET_KEY` | Ključ za potpisivanje JWT tokena. Token važi 30 dana. |
| `DATABASE_URL` | `sqlite:///basket.db` | SQLAlchemy URL baze. SQLite fajl završava u `instance/basket.db`. |
| `UPLOAD_FOLDER` | `uploads` | Koren za snimke i renderovane videe. |
| `MODEL_PATH` | `models/best.pt` | Putanja do YOLO težina. |
| `FFMPEG_PATH` | `ffmpeg` | Ime ili puna putanja ffmpeg binarnog fajla. `ffprobe` se traži pored njega. |

Fiksno u `config.py`: maksimalna veličina zahteva 500 MB, dozvoljene ekstenzije
snimaka `mp4`, `avi`, `mov`.

Primer `.env`:

```dotenv
SECRET_KEY=zameni-me-dugackim-random-stringom
DATABASE_URL=sqlite:///basket.db
UPLOAD_FOLDER=uploads
MODEL_PATH=models/best.pt
FFMPEG_PATH=ffmpeg
```

Generisanje tajnog ključa:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Baza i migracije

Šema se vodi kroz Flask-Migrate (Alembic), folder `migrations/`.

```bash
# primeni sve migracije (prvo pokretanje i posle svakog pull-a)
flask --app app.py db upgrade

# posle izmene modela u api/models.py: napravi novu migraciju, pregledaj je, primeni
flask --app app.py db migrate -m "opis izmene"
flask --app app.py db upgrade

# trenutna revizija, istorija, vraćanje jedne migracije nazad
flask --app app.py db current
flask --app app.py db history
flask --app app.py db downgrade -1
```

Tabele:

- `users`: `device_id` (jedinstven identifikator uređaja), `height`, `unit`, `language`,
  `is_right_handed`, `terms_accepted`.
- `jobs`: `job_id` (UUID), `user_id`, `front_video_path`, `side_video_path`, `status`
  (`uploaded` → `processing` → `completed` ili `failed`), `analysis_result` (JSON
  rezultat analize, uključujući URL-ove videa).

Brisanje baze u razvoju (gubi sve podatke):

```bash
rm -f instance/basket.db && flask --app app.py db upgrade
```

## Pokretanje

Razvojni server (debug, auto-reload, sluša na svim interfejsima, port 5000):

```bash
source venv/bin/activate
python app.py
```

Alternativno kroz Flask CLI:

```bash
flask --app app.py run --debug --host 0.0.0.0 --port 5000
```

Provera:

```bash
curl http://localhost:5000/
# Hello, World!
```

Za produkciju koristiti WSGI server, na primer gunicorn. **Bitno:** biblioteka nije
thread-safe, pa API serijalizuje analizu kroz jedan lock po procesu. Više workera
znači više paralelnih analiza, ali i više kopija modela u memoriji (po jedna po
procesu, učitava se pri prvom zahtevu). Timeout mora da pokrije trajanje analize.

```bash
pip install gunicorn
gunicorn -w 2 -b 0.0.0.0:5000 --timeout 600 app:app
```

## Brzi test sa curl-om

Ceo tok od registracije do preuzimanja videa. Snimci `videos/front/front_01.mp4` i
`videos/side/side_01.mp4` su primeri koji daju po jedan detektovan šut.

```bash
BASE=http://localhost:5000

# 1. Registracija uređaja (prvi put) → 201 i token
curl -s -X POST $BASE/login -H 'Content-Type: application/json' -d '{
  "device_id": "device-abc-123",
  "height": 185, "unit": "cm", "language": "sr",
  "is_right_handed": true, "terms_accepted": true
}'

# 1b. Login postojećeg uređaja → 200, token i profil
TOKEN=$(curl -s -X POST $BASE/login -H 'Content-Type: application/json' \
  -d '{"device_id": "device-abc-123"}' | python -c 'import sys,json; print(json.load(sys.stdin)["token"])')
echo $TOKEN

# 2. Izmena profila (ruka kojom šutira utiče na analizu)
curl -s -X PUT $BASE/profile -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"height": 182, "is_right_handed": true}'

# 3. Analiza (sinhrono; traje od nekoliko sekundi do više desetina sekundi)
curl -s -X POST $BASE/analyze -H "Authorization: Bearer $TOKEN" \
  -F "front_video=@videos/front/front_01.mp4" \
  -F "side_video=@videos/side/side_01.mp4" -o analyze.json -w "HTTP %{http_code}\n"

# 4. Pročitaj job_id i URL-ove videa iz odgovora
python -c "import json; b=json.load(open('analyze.json')); print(b['job_id']); print(*[v['url'] for v in b['videos']], sep='\n')"
JOB_ID=$(python -c "import json; print(json.load(open('analyze.json'))['job_id'])")

# 5. Preuzmi renderovane videe (front i side, šut 0)
curl -s -H "Authorization: Bearer $TOKEN" -o front_0.mp4 $BASE/result/$JOB_ID/front/0
curl -s -H "Authorization: Bearer $TOKEN" -o side_0.mp4  $BASE/result/$JOB_ID/side/0
ffprobe -v error -show_entries stream=codec_name,width,height -of csv=p=0 front_0.mp4
# h264,418,756  (dimenzije zavise od snimka; kadar je isečen oko igrača)

# 6. Status joba i istorija
curl -s -H "Authorization: Bearer $TOKEN" $BASE/status/$JOB_ID
curl -s -H "Authorization: Bearer $TOKEN" $BASE/history

# 7. Brisanje joba (numerički id iz odgovora, ne UUID); briše i fajlove sa diska
ID=$(python -c "import json; print(json.load(open('analyze.json'))['id'])")
curl -s -X DELETE -H "Authorization: Bearer $TOKEN" $BASE/history/$ID
```

Ako je izlaz JSON-a nečitljiv, dodaj `| python -m json.tool` na kraj komande.

## Postman kolekcija

Fajl `postman_collection.json` importuje se u Postman (Import → File). Sadrži sve
endpointe, test skripte i varijable, tako da posle importa nije potrebno ništa
ručno prepisivati:

| Varijabla | Šta je | Ko je puni |
|---|---|---|
| `base_url` | `http://localhost:5000` | ručno, ako server nije lokalno |
| `device_id` | identifikator uređaja | ručno |
| `jwt_token` | Bearer token za sve zahteve | automatski posle Register/Login |
| `job_db_id` | numerički `id` joba (za `/process` i `DELETE /history`) | automatski posle Analyze/Upload |
| `job_id` | UUID joba (za `/status` i `/result`) | automatski posle Analyze/Process |
| `front_video_path`, `side_video_path` | apsolutne putanje do snimaka na tvom računaru | ručno (podešeno na primere iz `uploads/`) |
| `result_camera`, `result_shot_idx` | koji video se traži u "Result video" | automatski iz prvog videa u odgovoru Analyze |

Redosled: **Auth → Login** (ili Register prvi put), **Analyze → Analyze front + side**,
**Analyze → Result video**. Kod "Result video" klikni strelicu pored dugmeta Send i
izaberi **Send and Download**, pa sačuvaj `.mp4`; obični Send prikazuje samo binarni
sadržaj. Pošto `/analyze` može da traje dugo, u Postman podešavanjima
(Settings → General → Request timeout) stavi 0 ili bar 300000 ms.

Posle svake izmene kolekcije u repozitorijumu ponovo je importuj (Import → Replace),
Postman ne prati promene fajla na disku.

## Endpointi

Svi endpointi osim `/` i `/login` traže header `Authorization: Bearer <token>`.
Greške se vraćaju kao `{"error": "..."}` sa odgovarajućim HTTP kodom; nevažeći ili
istekao token daje 401, nepostojeći korisnik 404.

### GET /

Provera da server radi. Bez autentikacije. Vraća tekst `Hello, World!`.

### POST /login

Jedan endpoint za registraciju i prijavu, po `device_id`.

- **Uređaj ne postoji (registracija)**: obavezna polja `device_id`, `height`, `unit`
  (npr. `cm`), `language` (npr. `sr`, `en`), `is_right_handed`, `terms_accepted`
  (mora biti `true`). Odgovor **201** `{"token": "..."}`.
- **Uređaj postoji (login)**: dovoljno `{"device_id": "..."}`. Odgovor **200**
  `{"token": "...", "user_profile": {...}}`.
- 400 ako nema `device_id`, nedostaju polja za registraciju ili uslovi nisu prihvaćeni.

```bash
curl -X POST http://localhost:5000/login -H 'Content-Type: application/json' \
  -d '{"device_id":"device-abc-123","height":185,"unit":"cm","language":"sr","is_right_handed":true,"terms_accepted":true}'
```

### PUT /profile

Menja profil. Dozvoljena polja: `height`, `unit`, `language`, `is_right_handed`.
`is_right_handed` određuje ruku (`right`/`left`) koja se prosleđuje analizi.
Odgovor 200 `{"message": "...", "user_profile": {...}}`.

```bash
curl -X PUT http://localhost:5000/profile -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"height":182,"language":"en","is_right_handed":false}'
```

### POST /analyze

Glavni endpoint. `multipart/form-data` sa dva fajla: `front_video` (spreda) i
`side_video` (sa strane). Dozvoljene ekstenzije `mp4`, `avi`, `mov`.

Šta radi, redom:

1. snima oba fajla u `uploads/<device_id>/<job_id>_front_<ime>` i `..._side_<ime>`;
2. kreira job sa statusom `processing`;
3. ako snimak nosi `rotate` metapodatke (telefon), fizički ga okrene ffmpeg-om i
   prepiše na istom mestu;
4. pušta analizu obe kamere (sinhrono, u okviru zahteva);
5. za svaki šut sa statusom `ok` renderuje anotirani video u
   `uploads/<device_id>/results/<job_id>/<camera>_<shot_idx>.mp4` (H.264);
6. upisuje rezultat u bazu i vraća ga.

Odgovori:

| Kod | Značenje |
|---|---|
| 200 | obe kamere obrađene, `status: completed` |
| 422 | biblioteka nije uspela da obradi neki snimak, `status: failed`; detalji u `result.<camera>.status` (`failed_video_open`, `failed_first_pass`, `failed_second_pass`). Druga kamera može imati validan rezultat i video. |
| 500 | analiza je pukla neočekivano, `status: failed` |
| 400 | nedostaje fajl, prazno ime ili nedozvoljena ekstenzija |

```bash
curl -X POST http://localhost:5000/analyze -H "Authorization: Bearer $TOKEN" \
  -F "front_video=@videos/front/front_01.mp4" -F "side_video=@videos/side/side_01.mp4"
```

Primer odgovora (skraćen):

```json
{
  "id": 7,
  "job_id": "92da0c0c-aece-42ee-a8fe-ef401a940247",
  "status": "completed",
  "shooting_hand": "right",
  "result": {
    "front": {
      "camera": "front", "shooting_hand": "right",
      "shots": [
        {
          "shot_idx": 0,
          "status": "ok",
          "phases": {"shot_start": 12, "set_points": [31], "release_point": 45,
                     "jump": {"start": 28, "top": 44, "end": 58}},
          "errors_per_frame": {"14": ["siroko stopalo"], "15": ["siroko stopalo", "lopta van tela"]},
          "error_label_counts": {"lopta van tela": 4, "siroko stopalo": 14},
          "video_url": "/result/92da0c0c-aece-42ee-a8fe-ef401a940247/front/0"
        }
      ]
    },
    "side": {"camera": "side", "shooting_hand": "right", "shots": [ ... ]}
  },
  "videos": [
    {"camera": "front", "shot_idx": 0, "url": "/result/92da0c0c-.../front/0"},
    {"camera": "side",  "shot_idx": 0, "url": "/result/92da0c0c-.../side/0"}
  ]
}
```

### GET /result/{job_id}/{camera}/{shot_idx}

Vraća renderovani video jednog šuta kao `video/mp4` (podržava range zahteve, pa može
direktno u `<video>` tag ili plejer). `job_id` je UUID, `camera` je `front` ili `side`,
`shot_idx` je `shot_idx` iz rezultata. URL-ovi se ne sklapaju ručno, već se čitaju iz
`videos[]` ili `shots[].video_url`.

- 400 ako `camera` nije `front`/`side`
- 404 ako job ne pripada korisniku ili video za taj šut ne postoji (na primer šut
  sa statusom `skipped_no_shot_phases`)

```bash
curl -H "Authorization: Bearer $TOKEN" -o front_0.mp4 \
  http://localhost:5000/result/$JOB_ID/front/0
```

### POST /upload, POST /process, GET /status/{job_id} (asinhroni tok)

Pripremljen tok za obradu u pozadini; **analiza se u njemu još ne pokreće** (`/process`
samo menja status u `processing`, obeleženo je kao TODO u kodu). Za stvarnu analizu
koristiti `/analyze`.

- `POST /upload`: isti `multipart` kao `/analyze`. Snima fajlove, kreira job sa
  statusom `uploaded`, vraća 201 `{"id": <numerički id>}`.
- `POST /process`: body `{"job_id": <numerički id iz /upload>}`. Prebacuje job iz
  `uploaded` u `processing`, vraća 202 `{"job_id": "<UUID>", "status": "processing"}`.
  400 ako job nije u statusu `uploaded`.
- `GET /status/{job_id}`: po UUID-u. Vraća `id`, `job_id`, `status`, `created_at`, a
  ako postoji rezultat i `analysis` (isto što i `result` iz `/analyze`) i `videos`.

```bash
ID=$(curl -s -X POST http://localhost:5000/upload -H "Authorization: Bearer $TOKEN" \
  -F "front_video=@videos/front/front_01.mp4" -F "side_video=@videos/side/side_01.mp4" \
  | python -c 'import sys,json; print(json.load(sys.stdin)["id"])')
curl -s -X POST http://localhost:5000/process -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d "{\"job_id\": $ID}"
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:5000/status/$JOB_ID
```

### GET /history

Svi jobovi korisnika, najnoviji prvi, u istom obliku kao `/status` (sa `analysis` i
`videos` kad postoje).

```bash
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:5000/history | python -m json.tool
```

### DELETE /history/{id}

Briše job po **numeričkom** `id`-u, zajedno sa front/side snimcima i celim folderom
renderovanih videa `uploads/<device_id>/results/<job_id>/`. Odgovor 200
`{"message": "Job deleted successfully"}`, 404 ako job ne postoji ili nije korisnikov.

```bash
curl -s -X DELETE -H "Authorization: Bearer $TOKEN" http://localhost:5000/history/7
```

## Format rezultata analize

Po kameri (`result.front`, `result.side`):

| Polje | Opis |
|---|---|
| `camera` | `front` ili `side` |
| `shooting_hand` | `right` ili `left`, iz profila |
| `status` | prisutno samo kad je cela kamera pala: `failed_video_open`, `failed_first_pass`, `failed_second_pass`; tada je i `error` sa porukom, a `shots` je prazan |
| `shots` | lista detektovanih šuteva u snimku |

Po šutu (`shots[i]`):

| Polje | Opis |
|---|---|
| `shot_idx` | redni broj šuta u snimku, od 0 |
| `status` | `ok`; `skipped_no_shot_phases` (nisu prepoznate faze, nema ostalih polja); `failed_error_detection` (pala detekcija grešaka, uz `error`) |
| `phases.shot_start` | frejm početka šuta (relativno na isečak šuta) |
| `phases.set_points` | frejmovi set pointa (lopta u položaju pred izbačaj) |
| `phases.release_point` | frejm izbačaja |
| `phases.jump` | `{start, top, end}` frejmovi skoka, ili `null` ako skok nije detektovan |
| `errors_per_frame` | mapa `"frejm" → [oznake grešaka]`, samo frejmovi koji imaju grešku |
| `error_label_counts` | zbirno: oznaka greške → u koliko frejmova se pojavila |
| `video_url` | putanja za `GET /result/...`; `null` ako renderovanje nije uspelo |

Oznake grešaka koje biblioteka trenutno prepoznaje:

- **front kamera**: `lakat presiroko`, `lopta van glave`, `lopta van tela`, `nakrivljenost`,
  `nesimetricno savijena kolena`, `nesuterski lakat na gore`, `pada nesuterska ruka`,
  `prenisko lopta`, `razdvajanje ruku presiroko`, `ruke idu u desno`, `ruke idu u levo`,
  `ruke se ukrstaju`, `siroko stopalo`, `usko stopalo`
- **side kamera**: `kontra ugao sake`, `lopta iza glave`, `nadlaktica ispred tela`,
  `nadlaktica iza tela`, `prave noge`, `predubok stav`

Snimak može da prođe analizu i sa praznom listom `shots` (na primer ako igrač nije
ceo u kadru ili šut nije prepoznat); tada je HTTP status 200, ali nema videa.

## Batch renderovanje bez API-ja

Skripta `scripts/render_videos.py` analizira sve snimke iz foldera i renderuje video
po šutu, bez servera, baze i autentikacije. Kamera se čita iz imena podfoldera
(`videos/front/`, `videos/side/`) ili iz prefiksa fajla (`front_01.mp4`).
Originali se ne menjaju (rade se na kopiji u privremenom folderu).

```bash
source venv/bin/activate

# videos/{front,side}/*.mp4 -> result_videos/<ime>_shot<N>.mp4 + summary.json
python scripts/render_videos.py

# bez MediaPipe skeleta (ostaju lopta, faza šuta i istaknute greške)
python scripts/render_videos.py --no-skeleton -o result_videos/no_skeleton

# drugi ulazni/izlazni folder, levoruk igrač
python scripts/render_videos.py -i /putanja/do/snimaka -o /putanja/do/izlaza --shooting-hand left

python scripts/render_videos.py --help
```

Izlaz: `result_videos/` je u `.gitignore`. `summary.json` sadrži isti rezultat kao
`result.<camera>` iz API-ja, plus `file` (izvorni snimak) i `rendered` (putanje videa).

Ista analiza može da se pusti i direktno kroz CLI biblioteke (piše u `result_videos/`
pored mesta odakle se pokreće, bez ispravljanja rotacije i bez H.264):

```bash
python -m suterska_ruka -p videos/front/front_01.mp4 -c front --shooting-hand right --model-path models/best.pt
```

## Kako radi obrada videa

Tok za jedan snimak (`api/analysis.py`):

1. **Rotacija.** Telefoni snimaju 1280×720 i upišu `rotate` metapodatak umesto da
   okrenu frejmove. OpenCV, kroz koji biblioteka čita snimak, to ignoriše, pa bi igrač
   bio položen, a i skelet i tekst na izlaznom videu. Zato se snimak pre analize
   prepakuje ffmpeg-om (koji rotaciju primeni) i prepiše na istom mestu.
2. **Analiza.** Biblioteka u prvom prolazu nađe igrača i kandidate za šuteve, u drugom
   prolazu za svaki šut pusti MediaPipe pozu i YOLO detekciju lopte na isečku oko
   igrača, pa odredi faze šuta i greške po frejmu. Model se učitava jednom po procesu,
   pri prvom zahtevu.
3. **Renderovanje.** Za svaki šut sa statusom `ok` biblioteka iscrta skelet, okvir lopte,
   fazu i istaknutu grešku u privremeni `mp4v` fajl, koji API prepakuje u H.264
   (`libx264`, `yuv420p`, `faststart`) da bi se puštao u browseru i na telefonu.
   Bez ffmpeg-a fajl se samo kopira.
4. **Konkurentnost.** Biblioteka nije thread-safe, a Flask obrađuje zahteve u više
   niti, pa se cela obrada (analiza + renderovanje) serijalizuje kroz jedan lock.
   Dva istovremena `/analyze` zahteva se izvršavaju jedan za drugim.

Raspored fajlova na disku za jedan job:

```
uploads/
└── device-abc-123/
    ├── 92da0c0c-..._front_front_01.mp4      # uploadovan (i ispravljen) front snimak
    ├── 92da0c0c-..._side_side_01.mp4        # uploadovan (i ispravljen) side snimak
    └── results/
        └── 92da0c0c-.../
            ├── front_0.mp4                  # renderovan šut 0, front kamera
            └── side_0.mp4                   # renderovan šut 0, side kamera
```

## Struktura projekta

```
basket-api/
├── app.py                    # ulazna tačka: python app.py
├── config.py                 # Config klasa, čita .env
├── requirements.txt          # Flask + pinovi za mediapipe/numpy/opencv/ultralytics
├── .env.example              # šablon konfiguracije
├── postman_collection.json   # Postman kolekcija svih endpointa
├── API Specifikacija.txt     # izvorna specifikacija API-ja
├── api/
│   ├── __init__.py           # Flask app, SQLAlchemy, Migrate, JWT, registracija ruta
│   ├── models.py             # User, Job (+ to_dict, result_videos)
│   ├── constants.py          # poruke grešaka i statusi jobova
│   ├── storage.py            # snimanje uploada, putanje rezultata, brisanje fajlova joba
│   ├── analysis.py           # integracija suterska-ruka: rotacija, analiza, renderovanje, H.264
│   └── routes/
│       ├── auth.py           # GET /, POST /login
│       ├── user.py           # PUT /profile, GET /history, DELETE /history/<id>
│       ├── analyze.py        # POST /analyze, GET /result/<job_id>/<camera>/<shot_idx>
│       └── video.py          # POST /upload, POST /process, GET /status/<job_id>
├── scripts/
│   └── render_videos.py      # batch analiza + renderovanje foldera bez API-ja
├── migrations/               # Alembic migracije (flask db ...)
├── models/best.pt            # YOLO težine (nije u gitu)
├── videos/{front,side}/      # primeri snimaka za test
├── uploads/                  # snimci korisnika i renderovani videi (nije u gitu)
└── instance/basket.db        # SQLite baza (nije u gitu)
```

## Česti problemi

**`pip install mediapipe==0.10.21` ne nalazi verziju.** Venv nije na Pythonu 3.12.
Proveri `python --version` unutar venv-a i napravi ga ponovo sa `python3.12 -m venv venv`.

**`ImportError`/konflikt numpy i opencv posle instalacije biblioteke.** Instalirana je
sa rezolucijom zavisnosti. Ponovi korak 4 sa `--no-deps`, pa `pip install -r requirements.txt`
da vrati pinove.

**`FileNotFoundError: models/best.pt` pri prvom `/analyze`.** Model nije na putanji iz
`MODEL_PATH`. Učitava se lenjo, pri prvom zahtevu, pa server normalno startuje bez njega.

**`/analyze` vraća 200, ali `shots` je prazan i nema videa.** Biblioteka nije prepoznala
šut (igrač nije ceo u kadru, loš ugao, prekratak ili predugačak snimak). To nije greška
API-ja; probaj sa primerima iz `videos/`.

**Video se skine, ali plejer ili browser ne može da ga pusti.** ffmpeg nije nađen, pa je
ostao `mp4v` kodek. Instaliraj ffmpeg ili podesi `FFMPEG_PATH`; u logu servera stoji
upozorenje `ffmpeg not found`.

**Igrač je položen na izlaznom videu.** Isto: bez ffmpeg-a/ffprobe-a rotacija snimka se
ne ispravlja.

**Postman prijavi timeout na `/analyze`.** Povećaj Request timeout u podešavanjima
Postmana (0 = bez ograničenja).

**`Address already in use` na portu 5000.** Već radi jedna instanca (`python app.py`
u drugom terminalu) ili drugi program. Ugasi je ili pokreni na drugom portu:
`flask --app app.py run --port 5001`.

**`Permission denied (publickey)` pri instalaciji biblioteke.** Nema SSH ključa za GitHub
na toj mašini; dodaj ključ ili zameni `git+ssh://git@github.com/` sa
`git+https://github.com/` uz token.

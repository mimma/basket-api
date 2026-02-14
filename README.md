# Basket API

Flask API projekat za obradu video snimaka.

## Instalacija

1. Kreirajte virtuelno okruženje:
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# ili
venv\Scripts\activate  # Windows
```

2. Instalirajte zavisnosti:
```bash
pip install -r requirements.txt
```

3. Kreirajte `.env` fajl (kopirajte `.env.example`):
```bash
cp .env.example .env
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

### 4. GET /status/{job_id}
Header: `Authorization: Bearer <token>`

### 5. GET /history
Header: `Authorization: Bearer <token>`

### 6. DELETE /history/{id}
Header: `Authorization: Bearer <token>`

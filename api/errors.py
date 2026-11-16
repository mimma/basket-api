"""Svi odgovori API-ja su JSON, i greske: `{"error": "<poruka>"}`.

Flask za 404/405/413/500 i flask-jwt-extended za neispravan token inace vracaju
HTML odnosno `{"msg": ...}`."""
import json

from werkzeug.exceptions import HTTPException

from flask import jsonify

from api import app
from api import jwt


@app.errorhandler(HTTPException)
def handle_http_error(e: HTTPException):
    # Werkzeug odgovor zadrzava kod i headere (npr. `Allow` kod 405), menja se samo telo.
    response = e.get_response()
    response.set_data(json.dumps({'error': e.description}))
    response.content_type = 'application/json'
    return response


@jwt.unauthorized_loader
@jwt.invalid_token_loader
def handle_missing_or_invalid_token(reason: str):
    return jsonify({'error': reason}), 401


@jwt.expired_token_loader
def handle_expired_token(_header, _payload):
    return jsonify({'error': 'Token has expired'}), 401

from flask import jsonify
from flask import request
from flask_jwt_extended import create_access_token

from api import app
from api import db
from api.constants import ERROR_DEVICE_ID_REQUIRED
from api.constants import ERROR_MISSING_REGISTRATION_FIELDS
from api.constants import ERROR_TERMS_NOT_ACCEPTED
from api.models import User


@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()

    if not data or 'device_id' not in data:
        return jsonify({'error': ERROR_DEVICE_ID_REQUIRED}), 400

    device_id = data['device_id']
    user = User.query.filter_by(device_id=device_id).first()

    # Scenario B: Login - User exists
    if user:
        token = create_access_token(identity=device_id)
        return jsonify({
            'token': token,
            'user_profile': user.to_dict()
        }), 200

    # Scenario A: Registration - First time
    required_fields = ['height', 'unit', 'language', 'is_right_handed', 'terms_accepted']
    if not all(field in data for field in required_fields):
        return jsonify({'error': ERROR_MISSING_REGISTRATION_FIELDS}), 400

    if not data['terms_accepted']:
        return jsonify({'error': ERROR_TERMS_NOT_ACCEPTED}), 400

    # Create new user
    new_user = User(device_id=device_id,
                    height=data['height'],
                    unit=data['unit'],
                    language=data['language'],
                    is_right_handed=data['is_right_handed'],
                    terms_accepted=data['terms_accepted']
                    )

    db.session.add(new_user)
    db.session.commit()

    token = create_access_token(identity=device_id)
    return jsonify({'token': token}), 201

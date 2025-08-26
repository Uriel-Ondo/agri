from flask import Blueprint, jsonify, request, current_app, render_template, make_response
from flask_login import login_required, current_user
from extensions import db, socketio, redis_client
from models import Session, Spectator
from datetime import datetime
import qrcode
import io
import base64
from PIL import Image
import uuid
import requests
import logging

# Configuration du logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

queue_bp = Blueprint('queue', __name__)

@queue_bp.route('/spectator/join/<int:session_id>', methods=['GET'])
def join_spectator_page(session_id):
    session = Session.query.get_or_404(session_id)
    if session.status != 'live':
        return render_template('error.html', error="La session n'est pas en cours"), 400
    
    spectator_id = request.cookies.get(f'spectator_id_{session_id}')
    if spectator_id:
        spectator = Spectator.query.filter_by(session_id=session_id, spectator_id=spectator_id).first()
        if spectator:
            return render_template('spectator.html', session_id=session_id, spectator_id=spectator_id)
    
    spectator = Spectator(
        session_id=session_id,
        status='pending',
        spectator_id=f"spectator_{uuid.uuid4().hex[:8]}",
        stream_key=f"spectator_{uuid.uuid4().hex[:8]}",
        timestamp=datetime.now()
    )
    db.session.add(spectator)
    db.session.commit()

    socketio.emit('queue_updated', {
        'session_id': session_id,
        'spectator_id': spectator.spectator_id,
        'status': spectator.status,
        'queue_position': Spectator.query.filter_by(session_id=session_id, status='pending').filter(Spectator.timestamp < spectator.timestamp).count()
    }, room=f'session_{session_id}')

    response = make_response(render_template('spectator.html', session_id=session_id, spectator_id=spectator.spectator_id))
    response.set_cookie(f'spectator_id_{session_id}', spectator.spectator_id, max_age=3600)
    return response

@queue_bp.route('/api/queue/<int:session_id>/toggle_qr', methods=['POST'])
@login_required
def toggle_qr(session_id):
    session = Session.query.get_or_404(session_id)
    if current_user.id != session.user_id and current_user.role != 'admin':
        return jsonify({'error': 'Non autorisé'}), 403

    show_qr = request.json.get('show', False)
    socketio.emit('toggle_qr_code', {
        'session_id': session_id,
        'show': show_qr,
        'qr_url': f"{current_app.config['PUBLIC_DOMAIN']}/spectator/join/{session_id}" if show_qr else ''
    }, room=f'session_{session_id}')
    return jsonify({'status': 'success', 'show': show_qr}), 200

@queue_bp.route('/api/queue/<int:session_id>/join', methods=['POST'])
def join_queue(session_id):
    session = Session.query.get_or_404(session_id)
    if session.status != 'live':
        return jsonify({'error': 'Session non en cours'}), 400

    spectator_id = request.json.get('spectator_id')
    spectator = Spectator.query.filter_by(session_id=session_id, spectator_id=spectator_id).first()
    if not spectator:
        spectator = Spectator(
            session_id=session_id,
            status='pending',
            spectator_id=f"spectator_{uuid.uuid4().hex[:8]}",
            stream_key=f"spectator_{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now()
        )
        db.session.add(spectator)
        db.session.commit()

    socketio.emit('queue_updated', {
        'session_id': session_id,
        'spectator_id': spectator.spectator_id,
        'status': spectator.status,
        'queue_position': Spectator.query.filter_by(session_id=session_id, status='pending').filter(Spectator.timestamp < spectator.timestamp).count()
    }, room=f'session_{session_id}')

    return jsonify({
        'status': 'success',
        'spectator_id': spectator.spectator_id,
        'stream_key': spectator.stream_key
    }), 201

@queue_bp.route('/api/queue/<int:session_id>/spectators', methods=['GET'])
@login_required
def get_queue(session_id):
    session = Session.query.get_or_404(session_id)
    if current_user.id != session.user_id and current_user.role != 'admin':
        return jsonify({'error': 'Non autorisé'}), 403

    spectators = Spectator.query.filter_by(session_id=session_id).order_by(Spectator.timestamp.asc()).all()
    return jsonify([{
        'spectator_id': s.spectator_id,
        'status': s.status,
        'timestamp': s.timestamp.isoformat(),
        'queue_position': Spectator.query.filter_by(session_id=session_id, status='pending').filter(Spectator.timestamp < s.timestamp).count()
    } for s in spectators])

@queue_bp.route('/api/queue/<int:session_id>/spectator/<string:spectator_id>/approve', methods=['POST'])
@login_required
def approve_spectator(session_id, spectator_id):
    session = Session.query.get_or_404(session_id)
    if current_user.id != session.user_id and current_user.role != 'admin':
        return jsonify({'error': 'Non autorisé'}), 403

    spectator = Spectator.query.filter_by(session_id=session_id, spectator_id=spectator_id).first_or_404()
    spectator.status = 'approved'
    db.session.commit()

    socketio.emit('spectator_approved', {
        'session_id': session_id,
        'spectator_id': spectator_id,
        'stream_key': spectator.stream_key
    }, room=f'session_{session_id}')

    return jsonify({'status': 'success'}), 200

@queue_bp.route('/api/queue/<int:session_id>/spectator/<string:spectator_id>/reject', methods=['POST'])
@login_required
def reject_spectator(session_id, spectator_id):
    session = Session.query.get_or_404(session_id)
    if current_user.id != session.user_id and current_user.role != 'admin':
        return jsonify({'error': 'Non autorisé'}), 403

    spectator = Spectator.query.filter_by(session_id=session_id, spectator_id=spectator_id).first_or_404()
    spectator.status = 'rejected'
    db.session.delete(spectator)
    db.session.commit()

    socketio.emit('queue_updated', {
        'session_id': session_id,
        'spectator_id': spectator_id,
        'status': 'rejected'
    }, room=f'session_{session_id}')
    socketio.emit('spectator_stream_stopped', {
        'session_id': session_id,
        'spectator_id': spectator_id
    }, room=f'session_{session_id}')

    return jsonify({'status': 'success'}), 200

@queue_bp.route('/api/queue/<int:session_id>/spectator/<string:spectator_id>/stop', methods=['POST'])
@login_required
def stop_spectator_stream(session_id, spectator_id):
    session = Session.query.get_or_404(session_id)
    if current_user.id != session.user_id and current_user.role != 'admin':
        return jsonify({'error': 'Non autorisé'}), 403

    spectator = Spectator.query.filter_by(session_id=session_id, spectator_id=spectator_id).first_or_404()
    spectator.status = 'ended'
    db.session.delete(spectator)
    db.session.commit()

    socketio.emit('spectator_stream_stopped', {
        'session_id': session_id,
        'spectator_id': spectator_id
    }, room=f'session_{session_id}')

    return jsonify({'status': 'success'}), 200

@queue_bp.route('/api/queue/<int:session_id>/qr', methods=['GET'])
def get_qr_code(session_id):
    session = Session.query.get_or_404(session_id)
    join_link = f"{current_app.config['PUBLIC_DOMAIN']}/spectator/join/{session_id}"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(join_link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    qr_code_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

    return jsonify({
        'qr_code': f"data:image/png;base64,{qr_code_base64}",
        'link': join_link
    })


@queue_bp.route('/api/queue/<int:session_id>/spectator/<string:spectator_id>/publish', methods=['POST'])
def publish_spectator_stream(session_id, spectator_id):
    session = Session.query.get_or_404(session_id)
    spectator = Spectator.query.filter_by(session_id=session_id, spectator_id=spectator_id).first_or_404()
    if spectator.status != 'approved':
        return jsonify({'error': 'Spectator not approved'}), 403
    data = request.json
    sdp_offer = data.get('sdp')
    if not sdp_offer:
        logger.error("Aucune offre SDP fournie dans la requête")
        return jsonify({'error': 'No SDP provided'}), 400
    if isinstance(sdp_offer, dict) and 'sdp' in sdp_offer:
        sdp_offer = sdp_offer['sdp']
    srs_api_url = f"http://{current_app.config['SRS_SERVER']}:{current_app.config['SRS_API_PORT']}/rtc/v1/publish/"
    stream_url = f"webrtc://{current_app.config['DOMAIN']}/live/{spectator.stream_key}"
    logger.debug(f"Envoi de l'offre SDP à SRS : {srs_api_url}")
    logger.debug(f"Stream URL : {stream_url}")
    logger.debug(f"Offre SDP : {sdp_offer}")
    try:
        test_response = requests.get(f"http://{current_app.config['SRS_SERVER']}:{current_app.config['SRS_API_PORT']}/api/v1/version", timeout=5)
        if test_response.status_code != 200:
            logger.error(f"API SRS inaccessible : {test_response.status_code} - {test_response.text}")
            return jsonify({'error': f'SRS API inaccessible: {test_response.status_code}'}), 500
        response = requests.post(srs_api_url, json={
            'sdp': sdp_offer,
            'streamurl': stream_url
        }, timeout=10)
        logger.debug(f"Réponse SRS : {response.status_code} - {response.text}")
        if response.status_code != 200:
            logger.error(f"Erreur SRS : {response.status_code} - {response.text}")
            return jsonify({'error': f'SRS server responded with status {response.status_code}: {response.text}'}), 500
        srs_response = response.json()
        if 'sdp' not in srs_response or not srs_response['sdp']:
            logger.error(f"Réponse SRS invalide : {srs_response}")
            return jsonify({'error': 'No SDP in response from SRS server'}), 500
        logger.debug(f"Réponse SDP : {srs_response['sdp']}")
        return jsonify({'sdp': {'type': 'answer', 'sdp': srs_response['sdp']}})
    except requests.RequestException as e:
        logger.error(f"Erreur lors de l'appel API SRS : {str(e)}")
        return jsonify({'error': f'SRS API error: {str(e)}'}), 500
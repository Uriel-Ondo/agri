from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_required, current_user
from extensions import db, socketio, redis_client
from app.models import Session, Question, Quiz
import uuid
from datetime import datetime, timedelta
import json

sessions_bp = Blueprint('sessions', __name__)

@sessions_bp.route('/create_session', methods=['GET', 'POST'])
@login_required
def create_session():
    if request.method == 'POST':
        try:
            title = request.form['title']
            description = request.form.get('description', '')
            start_time = datetime.strptime(request.form['start_time'], '%Y-%m-%dT%H:%M')
            end_time = datetime.strptime(request.form['end_time'], '%Y-%m-%dT%H:%M')
            current_time = datetime.now()

            if start_time <= current_time:
                flash("La date de début doit être dans le futur", 'danger')
                return redirect(url_for('sessions.create_session'))
                
            if end_time <= start_time:
                flash("La date de fin doit être après la date de début", 'danger')
                return redirect(url_for('sessions.create_session'))
                
            stream_key = f"session_{uuid.uuid4().hex[:8]}"
            session = Session(
                title=title,
                description=description,
                start_time=start_time,
                end_time=end_time,
                status='scheduled',
                stream_key=stream_key,
                user_id=current_user.id
            )
            
            db.session.add(session)
            db.session.commit()
            flash('Session créée avec succès !', 'success')
            return redirect(url_for('main.dashboard'))
            
        except ValueError as e:
            db.session.rollback()
            flash(f"Erreur de format de date: {str(e)}", 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f"Erreur lors de la création de la session: {str(e)}", 'danger')
            
    return render_template('create_session.html')

@sessions_bp.route('/session/<int:session_id>', methods=['GET', 'POST'])
@login_required
def manage_session(session_id):
    session = Session.query.get_or_404(session_id)
    
    if current_user.id != session.user_id and current_user.role != 'admin':
        flash('Action non autorisée', 'danger')
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        try:
            if 'start' in request.form:
                active_session = Session.query.filter_by(status='live').first()
                if active_session and active_session.id != session_id:
                    flash("Une autre session est déjà en cours. Veuillez arrêter la session en cours avant d'en démarrer une nouvelle.", 'danger')
                    return redirect(url_for('sessions.manage_session', session_id=session_id))
                    
                session.status = 'live'
                db.session.commit()
                socketio.emit('session_status_changed', {
                    'session_id': session_id,
                    'status': 'live'
                }, room=f'session_{session_id}')
                flash('Session démarrée avec succès !', 'success')
                
            elif 'stop' in request.form:
                session.status = 'ended'
                db.session.commit()
                socketio.emit('session_status_changed', {
                    'session_id': session_id,
                    'status': 'ended'
                }, room=f'session_{session_id}')
                flash('Session arrêtée avec succès !', 'success')
                
            elif 'answer' in request.form:
                question_id = request.form['question_id']
                answer_text = request.form['answer_text']
                
                question = Question.query.filter_by(
                    id=question_id,
                    session_id=session_id
                ).first_or_404()
                
                question.answer_text = answer_text
                db.session.commit()
                
                if redis_client:
                    redis_client.rpush(
                        f"session:{session_id}:questions",
                        f"Q:{question.question_text}|A:{answer_text}"
                    )
                
                socketio.emit('new_answer', {
                    'session_id': session_id,
                    'question_id': question.id,
                    'question_text': question.question_text,
                    'answer_text': answer_text,
                    'timestamp': question.timestamp.isoformat()
                }, room=f'session_{session_id}')
                
                flash('Réponse enregistrée avec succès !', 'success')
                
            elif 'delete_session' in request.form:
                Question.query.filter_by(session_id=session_id).delete()
                Quiz.query.filter_by(session_id=session_id).delete()
                db.session.delete(session)
                db.session.commit()
                
                flash('Session supprimée avec succès', 'success')
                return redirect(url_for('main.dashboard'))
                
        except Exception as e:
            db.session.rollback()
            flash(f"Erreur lors de la mise à jour: {str(e)}", 'danger')
    
    questions = Question.query.filter_by(session_id=session_id).order_by(Question.timestamp.asc()).all()
    quizzes = Quiz.query.filter_by(session_id=session_id).order_by(Quiz.timestamp.desc()).all()
    
    rtmp_url = f"rtmp://{current_app.config['SRS_SERVER']}:{current_app.config['SRS_RTMP_PORT']}/live/{session.stream_key}"
    hls_url = f"http://{current_app.config['SRS_SERVER']}:{current_app.config['SRS_HTTP_PORT']}/live/{session.stream_key}.m3u8"
    
    return render_template(
        'manage_session.html',
        session=session,
        questions=questions,
        quizzes=quizzes,
        rtmp_url=rtmp_url,
        hls_url=hls_url,
        rtmp_port=current_app.config['SRS_RTMP_PORT']
    )

@sessions_bp.route('/api/session/<int:session_id>/answer', methods=['POST'])
@login_required
def answer_question(session_id):
    if not current_user.is_authenticated:
        return jsonify({'error': 'Utilisateur non authentifié'}), 401

    session = Session.query.get_or_404(session_id)
    if current_user.id != session.user_id and current_user.role != 'admin':
        return jsonify({'error': 'Non autorisé'}), 403

    question_id = request.form.get('question_id')
    answer_text = request.form.get('answer_text')
    if not question_id or not answer_text:
        return jsonify({'error': 'Données manquantes'}), 400

    question = Question.query.filter_by(
        id=question_id,
        session_id=session_id
    ).first_or_404()

    try:
        question.answer_text = answer_text
        db.session.commit()

        if redis_client:
            redis_client.rpush(
                f"session:{session_id}:questions",
                f"Q:{question.question_text}|A:{answer_text}"
            )

        socketio.emit('new_answer', {
            'session_id': session_id,
            'question_id': question.id,
            'question_text': question.question_text,
            'answer_text': answer_text,
            'timestamp': question.timestamp.isoformat()
        }, room=f'session_{session_id}')

        return jsonify({
            'success': True,
            'question_id': question_id,
            'answer_text': answer_text
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Erreur lors de la soumission: {str(e)}'}), 500

@sessions_bp.route('/api/session/<int:session_id>/time_remaining', methods=['GET'])
@login_required
def time_remaining(session_id):
    session = Session.query.get_or_404(session_id)
    if current_user.id != session.user_id and current_user.role != 'admin':
        return jsonify({'error': 'Non autorisé'}), 403

    current_time = datetime.now()
    time_left = (session.end_time - current_time).total_seconds()
    
    if time_left <= 0:
        if session.status == 'live':
            session.status = 'ended'
            db.session.commit()
            socketio.emit('session_ended_auto', {
                'session_id': session_id,
                'message': 'La session a atteint sa date de fin et a été arrêtée automatiquement.'
            }, room=f'session_{session_id}')
        return jsonify({'time_left': 0, 'status': session.status})

    if time_left <= 300 and session.status == 'live':
        socketio.emit('session_time_warning', {
            'session_id': session_id,
            'message': 'Il reste moins de 5 minutes avant la fin de la session.'
        }, room=f'session_{session_id}')

    return jsonify({'time_left': max(0, time_left), 'status': session.status})

@sessions_bp.route('/session/<int:session_id>/delete', methods=['POST'])
@login_required
def delete_session(session_id):
    session = Session.query.get_or_404(session_id)
    
    if current_user.role != 'admin' and current_user.id != session.user_id:
        flash('Action non autorisée', 'danger')
        return redirect(url_for('main.dashboard'))
    
    try:
        with db.session.begin():
            Question.query.filter_by(session_id=session_id).delete()
            Quiz.query.filter_by(session_id=session_id).delete()
            db.session.delete(session)
            
        flash('Session supprimée avec succès', 'success')
        return redirect(url_for('admin.admin_dashboard' if current_user.role == 'admin' else 'main.dashboard'))
        
    except Exception as e:
        db.session.rollback()
        flash(f"Erreur lors de la suppression: {str(e)}", 'danger')
        return redirect(url_for('sessions.manage_session', session_id=session_id))

@sessions_bp.route('/live/<string:stream_key>')
def live_session(stream_key):
    session = Session.query.filter_by(stream_key=stream_key).first_or_404()
    
    if session.status != 'live':
        flash("Cette session n'est pas en cours de diffusion", 'warning')
        return redirect(url_for('main.dashboard'))
    
    hls_url = f"http://{current_app.config['SRS_SERVER']}:{current_app.config['SRS_HTTP_PORT']}/live/{session.stream_key}.m3u8"
    return render_template('live_session.html', session=session, hls_url=hls_url)
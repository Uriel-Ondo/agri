from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from extensions import db, socketio, redis_client
from models import Session, Question, Quiz, QuizResponse
import uuid
from datetime import datetime
import json
import logging

sessions_bp = Blueprint('sessions', __name__)

logger = logging.getLogger(__name__)

@sessions_bp.route('/create_session', methods=['GET', 'POST'])
@login_required
def create_session():
    if request.method == 'POST':
        try:
            title = request.form['title']
            description = request.form.get('description', '')
            start_time = datetime.strptime(request.form['start_time'], '%Y-%m-%dT%H:%M')
            end_time = datetime.strptime(request.form['end_time'], '%Y-%m-%dT%H:%M')
            
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
                # Suppression en cascade sécurisée
                logger.info(f"Tentative de suppression de la session {session_id}")
                
                # D'abord supprimer toutes les réponses aux quiz
                quiz_ids = [quiz.id for quiz in session.quizzes]
                if quiz_ids:
                    QuizResponse.query.filter(QuizResponse.quiz_id.in_(quiz_ids)).delete(synchronize_session=False)
                    db.session.flush()
                
                # Puis supprimer la session (les cascades s'occuperont du reste)
                db.session.delete(session)
                db.session.commit()
                
                flash('Session et tous ses contenus supprimés avec succès', 'success')
                return redirect(url_for('main.dashboard'))
                
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erreur lors de la suppression de la session {session_id}: {str(e)}")
            flash(f"Erreur lors de la suppression: {str(e)}", 'danger')
    
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

@sessions_bp.route('/session/<int:session_id>/delete', methods=['POST'])
@login_required
def delete_session(session_id):
    session = Session.query.get_or_404(session_id)
    
    if current_user.role != 'admin' and current_user.id != session.user_id:
        flash('Action non autorisée', 'danger')
        return redirect(url_for('main.dashboard'))
    
    try:
        logger.info(f"Suppression de la session {session_id} via la route dédiée")
        
        # D'abord supprimer toutes les réponses aux quiz
        quiz_ids = [quiz.id for quiz in session.quizzes]
        if quiz_ids:
            QuizResponse.query.filter(QuizResponse.quiz_id.in_(quiz_ids)).delete(synchronize_session=False)
            db.session.flush()
        
        # Puis supprimer la session
        db.session.delete(session)
        db.session.commit()
            
        flash('Session supprimée avec succès', 'success')
        return redirect(url_for('admin.admin_dashboard' if current_user.role == 'admin' else 'main.dashboard'))
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erreur lors de la suppression de la session {session_id}: {str(e)}")
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
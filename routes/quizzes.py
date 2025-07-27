from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from extensions import db, socketio, redis_client
from models import Session, Quiz, QuizResponse
from datetime import datetime
import json
import logging
from flask import current_app
from sqlalchemy import func

quizzes_bp = Blueprint('quizzes', __name__)
logger = logging.getLogger(__name__)

@quizzes_bp.route('/session/<int:session_id>/create_quiz', methods=['GET', 'POST'])
@login_required
def create_quiz(session_id):
    session = Session.query.get_or_404(session_id)
    
    if current_user.id != session.user_id and current_user.role != 'admin':
        flash('Action non autorisée', 'danger')
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        question = request.form['question']
        options = [
            request.form['option1'],
            request.form['option2'],
            request.form['option3'],
            request.form['option4']
        ]
        options = [opt for opt in options if opt.strip() != ""]
        if len(options) < 2:
            flash('Vous devez fournir au moins deux options valides', 'danger')
            return redirect(url_for('quizzes.create_quiz', session_id=session_id))
        
        correct_answer = int(request.form['correct_answer'])
        quiz = Quiz(
            session_id=session_id,
            question=question,
            options=options,
            correct_answer=correct_answer,
            timestamp=datetime.now()
        )
        db.session.add(quiz)
        db.session.commit()
        
        if hasattr(current_app, 'redis_client') and current_app.redis_client:
            current_app.redis_client.publish(f"session:{session_id}:quizzes", json.dumps({
                'id': quiz.id,
                'question': question,
                'options': options
            }))
        
        socketio.emit('new_quiz', {
            'session_id': session_id,
            'id': quiz.id,
            'question': question,
            'options': options,
            'timestamp': quiz.timestamp.isoformat()
        }, room=f'session_{session_id}')
        
        flash('Quiz créé avec succès !', 'success')
        return redirect(url_for('sessions.manage_session', session_id=session_id))
    
    return render_template('create_quiz.html', session=session)

@quizzes_bp.route('/session/<int:session_id>/quiz/<int:quiz_id>/delete', methods=['POST'])
@login_required
def delete_quiz(session_id, quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    session = Session.query.get_or_404(session_id)
    
    if current_user.id != session.user_id and current_user.role != 'admin':
        flash('Action non autorisée', 'danger')
        return redirect(url_for('sessions.manage_session', session_id=session_id))
    
    try:
        QuizResponse.query.filter_by(quiz_id=quiz_id).delete()
        db.session.delete(quiz)
        db.session.commit()
        flash('Quiz supprimé avec succès', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erreur lors de la suppression du quiz {quiz_id}: {str(e)}")
        flash(f'Erreur lors de la suppression du quiz: {str(e)}', 'danger')
    
    return redirect(url_for('sessions.manage_session', session_id=session_id))

@quizzes_bp.route('/session/<int:session_id>/quiz/<int:quiz_id>/respond', methods=['POST'])
def respond_quiz(session_id, quiz_id):
    try:
        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': 'Données invalides'}), 400
        
        device_id = data.get('device_id')
        selected_option = int(data.get('selected_option'))
        
        if not device_id:
            return jsonify({'status': 'error', 'message': 'ID d\'appareil manquant'}), 400
        
        # Vérifier si cet appareil a déjà répondu à ce quiz
        existing_response = QuizResponse.query.filter_by(
            quiz_id=quiz_id,
            device_id=device_id
        ).first()
        
        if existing_response:
            return jsonify({
                'status': 'error',
                'message': 'Vous avez déjà répondu à ce quiz'
            }), 400
        
        # Enregistrer la nouvelle réponse
        response = QuizResponse(
            quiz_id=quiz_id,
            device_id=device_id,  # Utilisation du device_id
            selected_option=selected_option,
            timestamp=datetime.now()
        )
        db.session.add(response)
        db.session.commit()
        
        socketio.emit('new_quiz_response', {
            'session_id': session_id,
            'quiz_id': quiz_id,
            'selected_option': selected_option
        }, room=f'session_{session_id}')
        
        return jsonify({'status': 'success'})
    
    except Exception as e:
        logger.error(f"Erreur lors de l'enregistrement de la réponse: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@quizzes_bp.route('/session/<int:session_id>/quiz/<int:quiz_id>/results')
@login_required
def quiz_results(session_id, quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    
    # Compter les réponses par option
    results = db.session.query(
        QuizResponse.selected_option,
        func.count(QuizResponse.id).label('count')
    ).filter_by(quiz_id=quiz_id).group_by(QuizResponse.selected_option).all()
    
    # Convertir en format facile à utiliser
    results_dict = {opt: 0 for opt in range(len(quiz.options))}
    for r in results:
        results_dict[r.selected_option] = r.count
    
    return render_template(
        'quiz_results.html', 
        quiz=quiz, 
        results=results_dict,
        session_id=session_id,
        total_responses=sum(results_dict.values())
    )
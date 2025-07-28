from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from extensions import db, socketio, redis_client
from app.models import Session, Quiz, QuizResponse
from datetime import datetime
import json
from flask import current_app

quizzes_bp = Blueprint('quizzes', __name__)

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
        socketio.emit('quiz_deleted', {
            'session_id': session_id,
            'quiz_id': quiz_id
        }, room=f'session_{session_id}')
        flash('Quiz supprimé avec succès', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erreur lors de la suppression du quiz: {str(e)}', 'danger')
    
    return redirect(url_for('sessions.manage_session', session_id=session_id))

@quizzes_bp.route('/session/<int:session_id>/quiz/<int:quiz_id>/respond', methods=['POST'])
@login_required
def respond_quiz(session_id, quiz_id):
    selected_option = int(request.form['selected_option'])
    response = QuizResponse(
        quiz_id=quiz_id,
        user_id=current_user.id,
        selected_option=selected_option,
        timestamp=datetime.now()
    )
    db.session.add(response)
    db.session.commit()
    socketio.emit('new_quiz_response', {
        'session_id': session_id,
        'quiz_id': quiz_id,
        'selected_option': selected_option,
        'correct_option': Quiz.query.get(quiz_id).correct_answer
    }, room=f'session_{session_id}')
    return jsonify({'status': 'success'})

@quizzes_bp.route('/session/<int:session_id>/quiz/<int:quiz_id>/results')
@login_required
def quiz_results(session_id, quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    session = Session.query.get_or_404(session_id)
    
    if current_user.id != session.user_id and current_user.role != 'admin':
        flash('Action non autorisée', 'danger')
        return redirect(url_for('sessions.manage_session', session_id=session_id))
    
    responses = QuizResponse.query.filter_by(quiz_id=quiz_id).all()
    results = [0] * len(quiz.options)
    for response in responses:
        results[response.selected_option] += 1
    return render_template('quiz_results.html', quiz=quiz, results=results, session_id=session_id)

@quizzes_bp.route('/api/session/<int:session_id>/quiz/<int:quiz_id>/results', methods=['GET'])
@login_required
def api_quiz_results(session_id, quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    session = Session.query.get_or_404(session_id)
    
    if current_user.id != session.user_id and current_user.role != 'admin':
        return jsonify({'error': 'Action non autorisée'}), 403
    
    responses = QuizResponse.query.filter_by(quiz_id=quiz_id).all()
    results = [0] * len(quiz.options)
    for response in responses:
        results[response.selected_option] += 1
    
    return jsonify({
        'quiz_id': quiz_id,
        'session_id': session_id,
        'question': quiz.question,
        'options': quiz.options,
        'results': results,
        'correct_option': quiz.correct_answer
    })
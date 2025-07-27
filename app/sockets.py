from flask_socketio import join_room, leave_room, emit
from flask import request
from app.models import Question, QuizResponse, Session, Quiz, db
from datetime import datetime

def register_handlers(socketio, redis_client, db):
    @socketio.on('connect')
    def handle_connect():
        print(f'Client connected: {request.sid}')

    @socketio.on('join_session')
    def handle_join_session(data):
        session_id = data.get('session_id')
        if session_id:
            join_room(f'session_{session_id}')
            print(f'Client {request.sid} joined session {session_id}')
            
            questions = Question.query.filter_by(session_id=session_id).order_by(Question.timestamp.asc()).all()
            for question in questions:
                emit('new_question', {
                    'session_id': session_id,
                    'question_id': question.id,
                    'question_text': question.question_text,
                    'answer_text': question.answer_text,
                    'timestamp': question.timestamp.isoformat()
                }, room=request.sid)
            
            quizzes = Quiz.query.filter_by(session_id=session_id).order_by(Quiz.timestamp.desc()).all()
            for quiz in quizzes:
                emit('new_quiz', {
                    'session_id': session_id,
                    'id': quiz.id,
                    'question': quiz.question,
                    'options': quiz.options,
                    'timestamp': quiz.timestamp.isoformat()
                }, room=request.sid)

    @socketio.on('leave_session')
    def handle_leave_session(data):
        session_id = data.get('session_id')
        if session_id:
            leave_room(f'session_{session_id}')
            print(f'Client {request.sid} left session {session_id}')

    @socketio.on('disconnect')
    def handle_disconnect():
        print(f'Client disconnected: {request.sid}')

    @socketio.on('question')
    def handle_question(data):
        session_id = data['session_id']
        question_text = data['question_text']
        question = Question(session_id=session_id, question_text=question_text, timestamp=datetime.now())
        db.session.add(question)
        db.session.commit()
        if redis_client:
            redis_client.rpush(f"session:{session_id}:questions", f"Q:{question_text}|A:")
        emit('new_question', {
            'session_id': session_id,
            'question_id': question.id,
            'question_text': question_text,
            'timestamp': question.timestamp.isoformat()
        }, room=f'session_{session_id}')

    @socketio.on('quiz_response')
    def handle_quiz_response(data):
        session_id = data['session_id']
        quiz_id = data['quiz_id']
        selected_option = data['selected_option']
        response = QuizResponse(
            quiz_id=quiz_id,
            user_id=None,
            selected_option=selected_option,
            timestamp=datetime.now()
        )
        db.session.add(response)
        db.session.commit()
        if redis_client:
            redis_client.rpush(f"session:{session_id}:quiz_responses", f"Q:{quiz_id}|A:{selected_option}")
        emit('new_quiz_response', {
            'session_id': session_id,
            'quiz_id': quiz_id,
            'selected_option': selected_option
        }, room=f'session_{session_id}')
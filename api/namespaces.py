from flask_restx import Resource, fields
from extensions import api
from models import Session, Question, Quiz, QuizResponse
from flask import jsonify, current_app
from datetime import datetime
from extensions import redis_client, socketio, db

# Création des namespaces
ns_session = api.namespace('sessions', description='Session operations')
ns_question = api.namespace('session/questions', description='Session question operations')

# Définition des modèles
session_model = api.model('Session', {
    'id': fields.Integer,
    'title': fields.String,
    'description': fields.String,
    'start_time': fields.DateTime,
    'end_time': fields.DateTime,
    'status': fields.String,
    'stream_key': fields.String,
    'user_id': fields.Integer,
    'hls_url': fields.String
})

quiz_model = api.model('Quiz', {
    'id': fields.Integer,
    'question': fields.String,
    'options': fields.List(fields.String),
    'correct_answer': fields.Integer
})

question_model = api.model('Question', {
    'id': fields.Integer,
    'session_id': fields.Integer,
    'question_text': fields.String,
    'answer_text': fields.String,
    'timestamp': fields.DateTime
})

# Ressources API
@ns_session.route('/current')
class CurrentSession(Resource):
    @ns_session.doc('get_current_session')
    @ns_session.marshal_with(session_model)
    def get(self):
        session = Session.query.filter_by(status='live').first()
        if session:
            return {
                'id': session.id,
                'title': session.title,
                'description': session.description,
                'start_time': session.start_time,
                'end_time': session.end_time,
                'status': session.status,
                'stream_key': session.stream_key,
                'user_id': session.user_id,
                'hls_url': f"https://{current_app.config['PUBLIC_DOMAIN']}/live/{session.stream_key}.m3u8"
            }
        return {'message': 'No live session'}, 404

@ns_question.route('/<int:session_id>/question')
class QuestionOperations(Resource):
    @ns_question.expect(api.model('QuestionInput', {
        'question_text': fields.String(required=True)
    }))
    @ns_question.doc('submit_question')
    def post(self, session_id):
        data = api.payload
        question_text = data['question_text']
        question = Question(session_id=session_id, question_text=question_text, timestamp=datetime.now())
        db.session.add(question)
        db.session.commit()
        redis_client.rpush(f"session:{session_id}:questions", f"Q:{question_text}|A:")
        socketio.emit('new_question', {
            'session_id': session_id,
            'question_id': question.id,
            'question_text': question_text,
            'timestamp': question.timestamp.isoformat()
        }, room=f'session_{session_id}')
        return {'status': 'success', 'question_id': question.id}, 201

    @ns_question.doc('get_session_questions')
    def get(self, session_id):
        questions = Question.query.filter_by(session_id=session_id).order_by(Question.timestamp.asc()).all()
        return jsonify([{
            'id': q.id,
            'question_text': q.question_text,
            'answer_text': q.answer_text,
            'timestamp': q.timestamp.isoformat()
        } for q in questions])

@ns_session.route('/<int:session_id>/quizzes')
class SessionQuizzes(Resource):
    @ns_session.doc('get_session_quizzes')
    @ns_session.marshal_list_with(quiz_model)
    def get(self, session_id):
        quizzes = Quiz.query.filter_by(session_id=session_id).all()
        return [{
            'id': quiz.id,
            'question': quiz.question,
            'options': quiz.options,
            'correct_answer': quiz.correct_answer
        } for quiz in quizzes])

@ns_session.route('/<int:session_id>/quiz/<int:quiz_id>/response')
class QuizResponseAPI(Resource):
    @ns_session.expect(api.model('QuizResponseInput', {
        'selected_option': fields.Integer(required=True)
    }))
    @ns_session.doc('submit_quiz_response')
    def post(self, session_id, quiz_id):
        data = api.payload
        selected_option = data['selected_option']
        response = QuizResponse(
            quiz_id=quiz_id,
            user_id=None,
            selected_option=selected_option,
            timestamp=datetime.now()
        )
        db.session.add(response)
        db.session.commit()
        redis_client.rpush(f"session:{session_id}:quiz_responses", f"Q:{quiz_id}|A:{selected_option}")
        socketio.emit('new_quiz_response', {
            'session_id': session_id,
            'quiz_id': quiz_id,
            'selected_option': selected_option
        }, room=f'session_{session_id}')
        return {'status': 'success'}, 201

@ns_session.route('/<int:session_id>/quiz/<int:quiz_id>/results')
class QuizResults(Resource):
    @ns_session.doc('get_quiz_results')
    def get(self, session_id, quiz_id):
        session = Session.query.get_or_404(session_id)
        quiz = Quiz.query.filter_by(id=quiz_id, session_id=session_id).first_or_404()
        responses = QuizResponse.query.filter_by(quiz_id=quiz_id).all()
        results = [0] * len(quiz.options)
        for response in responses:
            results[response.selected_option] += 1
        return jsonify({
            'quiz_id': quiz_id,
            'question': quiz.question,
            'options': quiz.options,
            'results': results
        })

def load_namespaces():
    # Cette fonction est appelée pour s'assurer que les namespaces sont chargés
    pass
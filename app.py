import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, Blueprint
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from redis import Redis
from flask_migrate import Migrate
import uuid
from datetime import datetime
from flask_restx import Api, Resource, fields, Namespace
from flask_socketio import SocketIO
import json

load_dotenv()

app = Flask(__name__)
socketio = SocketIO(app)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI')
app.config['SRS_SERVER'] = os.getenv('SRS_SERVER', 'localhost')
app.config['SRS_RTMP_PORT'] = int(os.getenv('SRS_RTMP_PORT', 1935))
app.config['SRS_HTTP_PORT'] = int(os.getenv('SRS_HTTP_PORT', 8080))

db = SQLAlchemy(app)
migrate = Migrate(app, db)

redis_client = Redis(
    host=os.getenv('REDIS_HOST'),
    port=int(os.getenv('REDIS_PORT', 6379)),
    db=int(os.getenv('REDIS_DB', 0))
)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Modèle Utilisateur
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False)

# Modèle Session
class Session(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False)
    stream_key = db.Column(db.String(50), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# Modèle Question
class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('session.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    answer_text = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, nullable=False)

# Modèle Quiz
class Quiz(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('session.id'), nullable=False)
    question = db.Column(db.Text, nullable=False)
    options = db.Column(db.JSON, nullable=False)
    correct_answer = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False)

# Modèle QuizResponse
class QuizResponse(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quiz.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # Nullable pour les agriculteurs non identifiés
    selected_option = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

api_bp = Blueprint('api', __name__, url_prefix='/api')
api = Api(api_bp, version='1.0', title='AgriAssist API', description='API documentation for AgriAssist streaming platform', doc='/apidocs/', default='AgriAssist', default_label='API endpoints')
app.register_blueprint(api_bp)

@app.route('/', methods=['GET'])
def home():
    return redirect(url_for('index'))

@app.route('/index')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash('Connexion réussie !', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Email ou mot de passe incorrect', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        if password != confirm_password:
            flash('Les mots de passe ne correspondent pas', 'danger')
            return redirect(url_for('register'))
        existing_username = User.query.filter_by(username=username).first()
        if existing_username:
            flash('Ce nom d\'utilisateur est déjà pris', 'danger')
            return redirect(url_for('register'))
        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            flash('Cet email est déjà utilisé', 'danger')
            return redirect(url_for('register'))
        new_user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            role='expert'
        )
        db.session.add(new_user)
        db.session.commit()
        flash('Compte créé avec succès ! Vous pouvez vous connecter', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Déconnexion réussie', 'success')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    sessions = Session.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', sessions=sessions)

@app.route('/create_session', methods=['GET', 'POST'])
@login_required
def create_session():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        start_time = datetime.strptime(request.form['start_time'], '%Y-%m-%dT%H:%M')
        end_time = datetime.strptime(request.form['end_time'], '%Y-%m-%dT%H:%M')
        stream_key = f"session_{uuid.uuid4().hex[:8]}"
        session = Session(title=title, description=description, start_time=start_time,
                         end_time=end_time, status='scheduled', stream_key=stream_key,
                         user_id=current_user.id)
        db.session.add(session)
        db.session.commit()
        flash('Session créée avec succès !', 'success')
        return redirect(url_for('dashboard'))
    return render_template('create_session.html')

@app.route('/session/<int:session_id>', methods=['GET', 'POST'])
@login_required
def manage_session(session_id):
    session = Session.query.get_or_404(session_id)
    if request.method == 'POST':
        if 'start' in request.form:
            session.status = 'live'
            db.session.commit()
            flash('Session démarrée avec succès !', 'success')
        elif 'stop' in request.form:
            session.status = 'ended'
            db.session.commit()
            flash('Session arrêtée avec succès !', 'success')
        elif 'answer' in request.form:
            question_id = request.form['question_id']
            answer_text = request.form['answer_text']
            question = Question.query.get_or_404(question_id)
            question.answer_text = answer_text
            db.session.commit()
            redis_client.rpush(f"session:{session_id}:questions", f"Q:{question.question_text}|A:{answer_text}")
            flash('Réponse enregistrée avec succès !', 'success')
    questions = Question.query.filter_by(session_id=session_id).all()
    quizzes = Quiz.query.filter_by(session_id=session_id).order_by(Quiz.timestamp.desc()).all()
    rtmp_url = f"rtmp://{app.config['SRS_SERVER']}:{app.config['SRS_RTMP_PORT']}/live/{session.stream_key}"
    hls_url = f"http://{app.config['SRS_SERVER']}:{app.config['SRS_HTTP_PORT']}/live/{session.stream_key}.m3u8"
    rtmp_port = app.config['SRS_RTMP_PORT']
    return render_template('manage_session.html', session=session, questions=questions, rtmp_url=rtmp_url, hls_url=hls_url, rtmp_port=rtmp_port, quizzes=quizzes)

@app.route('/session/<int:session_id>/create_quiz', methods=['GET', 'POST'])
@login_required
def create_quiz(session_id):
    session = Session.query.get_or_404(session_id)
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
            return redirect(url_for('create_quiz', session_id=session_id))
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
        redis_client.publish(f"session:{session_id}:quizzes", json.dumps({
            'id': quiz.id,
            'question': question,
            'options': options
        }))
        flash('Quiz créé avec succès !', 'success')
        return redirect(url_for('manage_session', session_id=session_id))
    return render_template('create_quiz.html', session=session)

@app.route('/session/<int:session_id>/quiz/<int:quiz_id>/respond', methods=['POST'])
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
    return jsonify({'status': 'success'})

@app.route('/session/<int:session_id>/quiz/<int:quiz_id>/results')
@login_required
def quiz_results(session_id, quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    responses = QuizResponse.query.filter_by(quiz_id=quiz_id).all()
    results = [0] * len(quiz.options)
    for response in responses:
        results[response.selected_option] += 1
    return render_template('quiz_results.html', quiz=quiz, results=results, session_id=session_id)

@app.route('/live/<string:stream_key>')
def live_session(stream_key):
    session = Session.query.filter_by(stream_key=stream_key).first_or_404()
    hls_url = f"http://{app.config['SRS_SERVER']}:{app.config['SRS_HTTP_PORT']}/live/{session.stream_key}.m3u8"
    return render_template('live_session.html', session=session, hls_url=hls_url)

ns_session = Namespace('sessions', description='Session operations')
api.add_namespace(ns_session)

ns_question = Namespace('session', description='Session question operations', path='/session')
api.add_namespace(ns_question)

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
                'hls_url': f"http://{app.config['SRS_SERVER']}:{app.config['SRS_HTTP_PORT']}/live/{session.stream_key}.m3u8"
            }
        return {'message': 'No live session'}, 404

@ns_question.route('/<int:session_id>/question', methods=['POST'])
class SubmitQuestion(Resource):
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
        return {'status': 'success', 'question_id': question.id}, 201

@ns_question.route('/<int:session_id>/questions', methods=['GET'])
class SessionQuestions(Resource):
    @ns_question.doc('get_session_questions')
    def get(self, session_id):
        questions = redis_client.lrange(f"session:{session_id}:questions", 0, -1)
        return jsonify([q.decode('utf-8').split('|') for q in questions])

@ns_session.route('/<int:session_id>/quizzes')
class SessionQuizzes(Resource):
    @ns_session.doc('get_session_quizzes')
    def get(self, session_id):
        quizzes = Quiz.query.filter_by(session_id=session_id).all()
        return jsonify([{
            'id': quiz.id,
            'question': quiz.question,
            'options': quiz.options,
            'correct_answer': quiz.correct_answer
        } for quiz in quizzes])

@ns_session.route('/<int:session_id>/quiz/<int:quiz_id>/response', methods=['POST'])
class QuizResponse(Resource):
    @ns_session.expect(api.model('QuizResponseInput', {
        'selected_option': fields.Integer(required=True)
    }))
    @ns_session.doc('submit_quiz_response')
    def post(self, session_id, quiz_id):
        data = api.payload
        selected_option = data['selected_option']
        response = QuizResponse(
            quiz_id=quiz_id,
            user_id=None,  # Agriculteurs non identifiés
            selected_option=selected_option,
            timestamp=datetime.now()
        )
        db.session.add(response)
        db.session.commit()
        redis_client.rpush(f"session:{session_id}:quiz_responses", f"Q:{quiz_id}|A:{selected_option}")
        return {'status': 'success'}, 201

@ns_session.route('/<int:session_id>/quiz/<int:quiz_id>/results', methods=['GET'])
class QuizResults(Resource):
    @ns_session.doc('get_quiz_results')
    def get(self, session_id, quiz_id):
        quiz = Quiz.query.get_or_404(quiz_id)
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

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, debug=True)
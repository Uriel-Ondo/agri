import os
import json
import uuid
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, Blueprint, send_from_directory
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from redis import Redis
from flask_migrate import Migrate
from flask_restx import Api, Resource, fields, Namespace
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS
from config import Config
from models import db, User, Session, Question, Quiz, QuizResponse

app = Flask(__name__)
app.config.from_object(Config)

CORS(app, resources={r"/api/*": {"origins": "*"}, r"/live/*": {"origins": "*"}})
socketio = SocketIO(app, 
                   cors_allowed_origins="*", 
                   async_mode='gevent',
                   logger=True,
                   engineio_logger=True,
                   ping_timeout=60,
                   ping_interval=25)

# Initialiser la base de données
db.init_app(app)
migrate = Migrate(app, db)

redis_client = Redis(
    host=app.config['REDIS_HOST'],
    port=app.config['REDIS_PORT'],
    db=app.config['REDIS_DB']
)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Création du blueprint et de l'API
api_bp = Blueprint('api', __name__,url_prefix='/api')
api = Api(
    app=api_bp,
    version='1.0',
    title='AgriAssist API',
    description='API documentation for AgriAssist streaming platform',
    doc='/apidocs/',  # Ceci définit le chemin de la documentation
    default='AgriAssist',
    default_label='API endpoints'
)

# Enregistrer le blueprint API après avoir défini toutes les routes
app.register_blueprint(api_bp)

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

# Création des namespaces
ns_session = api.namespace('sessions', description='Session operations')
ns_question = api.namespace('session/questions', description='Session question operations')

# Définition des ressources de l'API
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
        } for quiz in quizzes]

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


# Routes Flask standard
@app.route('/hbbtv')
def hbbtv():
    return render_template('hbbtv_index.html')

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static/images'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

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
            next_page = url_for('admin_dashboard') if user.role == 'admin' else url_for('dashboard')
            return redirect(next_page)
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

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.email = request.form['email']
        current_password = request.form['current_password']
        
        if not check_password_hash(current_user.password_hash, current_password):
            flash('Mot de passe actuel incorrect', 'danger')
            return redirect(url_for('profile'))
        
        if request.form['new_password']:
            if request.form['new_password'] != request.form['confirm_password']:
                flash('Les nouveaux mots de passe ne correspondent pas', 'danger')
                return redirect(url_for('profile'))
            
            current_user.password_hash = generate_password_hash(request.form['new_password'])
        
        db.session.commit()
        flash('Profil mis à jour avec succès', 'success')
        return redirect(url_for('profile'))
    
    return render_template('profile.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Déconnexion réussie', 'success')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    
    sessions = Session.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', sessions=sessions)

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        flash('Accès non autorisé', 'danger')
        return redirect(url_for('dashboard'))
    
    users = User.query.all()
    sessions = Session.query.all()
    return render_template('admin_dashboard.html', users=users, sessions=sessions)

@app.route('/admin/user/create', methods=['GET', 'POST'])
@login_required
def admin_create_user():
    if current_user.role != 'admin':
        flash('Accès non autorisé', 'danger')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        
        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            flash('Nom d\'utilisateur ou email déjà utilisé', 'danger')
            return redirect(url_for('admin_create_user'))
        
        new_user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            role=role
        )
        db.session.add(new_user)
        db.session.commit()
        flash('Utilisateur créé avec succès', 'success')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('admin_create_user.html')

@app.route('/admin/user/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
def admin_edit_user(user_id):
    if current_user.role != 'admin':
        flash('Accès non autorisé', 'danger')
        return redirect(url_for('dashboard'))
    
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        user.username = request.form['username']
        user.email = request.form['email']
        user.role = request.form['role']
        
        if request.form['password']:
            user.password_hash = generate_password_hash(request.form['password'])
        
        db.session.commit()
        flash('Utilisateur mis à jour avec succès', 'success')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('admin_edit_user.html', user=user)

@app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@login_required
def admin_delete_user(user_id):
    if current_user.role != 'admin':
        flash('Accès non autorisé', 'danger')
        return redirect(url_for('dashboard'))
    
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Vous ne pouvez pas supprimer votre propre compte', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    db.session.delete(user)
    db.session.commit()
    flash('Utilisateur supprimé avec succès', 'success')
    return redirect(url_for('admin_dashboard'))

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
    
    # Vérifier que l'utilisateur est l'expert propriétaire ou admin
    if current_user.id != session.user_id and current_user.role != 'admin':
        flash('Action non autorisée', 'danger')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
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
            question = Question.query.get_or_404(question_id)
            question.answer_text = answer_text
            db.session.commit()
            redis_client.rpush(f"session:{session_id}:questions", f"Q:{question.question_text}|A:{answer_text}")
            socketio.emit('new_answer', {
                'session_id': session_id,
                'question_id': question_id,
                'question_text': question.question_text,
                'answer_text': answer_text,
                'timestamp': question.timestamp.isoformat()
            }, room=f'session_{session_id}')
            flash('Réponse enregistrée avec succès !', 'success')
        elif 'delete_session' in request.form:
            db.session.delete(session)
            db.session.commit()
            flash('Session supprimée avec succès', 'success')
            return redirect(url_for('dashboard'))
    
    questions = Question.query.filter_by(session_id=session_id).order_by(Question.timestamp.asc()).all()
    quizzes = Quiz.query.filter_by(session_id=session_id).order_by(Quiz.timestamp.desc()).all()
    rtmp_url = f"rtmp://{app.config['SRS_SERVER']}:{app.config['SRS_RTMP_PORT']}/live/{session.stream_key}"
    hls_url = f"http://{app.config['SRS_SERVER']}:{app.config['SRS_HTTP_PORT']}/live/{session.stream_key}.m3u8"
    rtmp_port = app.config['SRS_RTMP_PORT']
    return render_template('manage_session.html', session=session, questions=questions, 
                         rtmp_url=rtmp_url, hls_url=hls_url, rtmp_port=rtmp_port, quizzes=quizzes)

@app.route('/session/<int:session_id>/delete', methods=['POST'])
@login_required
def delete_session(session_id):
    session = Session.query.get_or_404(session_id)
    
    # Vérifier que l'utilisateur est admin ou l'expert propriétaire
    if current_user.role != 'admin' and current_user.id != session.user_id:
        flash('Action non autorisée', 'danger')
        return redirect(url_for('dashboard'))
    
    db.session.delete(session)
    db.session.commit()
    flash('Session supprimée avec succès', 'success')
    return redirect(url_for('admin_dashboard' if current_user.role == 'admin' else 'dashboard'))

@app.route('/session/<int:session_id>/create_quiz', methods=['GET', 'POST'])
@login_required
def create_quiz(session_id):
    session = Session.query.get_or_404(session_id)
    
    # Vérifier que l'utilisateur est l'expert propriétaire ou admin
    if current_user.id != session.user_id and current_user.role != 'admin':
        flash('Action non autorisée', 'danger')
        return redirect(url_for('dashboard'))
    
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
        socketio.emit('new_quiz', {
            'session_id': session_id,
            'id': quiz.id,
            'question': question,
            'options': options,
            'timestamp': quiz.timestamp.isoformat()
        }, room=f'session_{session_id}')
        flash('Quiz créé avec succès !', 'success')
        return redirect(url_for('manage_session', session_id=session_id))
    return render_template('create_quiz.html', session=session)

@app.route('/session/<int:session_id>/quiz/<int:quiz_id>/delete', methods=['POST'])
@login_required
def delete_quiz(session_id, quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    session = Session.query.get_or_404(session_id)
    
    # Vérifier que l'utilisateur est l'expert propriétaire ou admin
    if current_user.id != session.user_id and current_user.role != 'admin':
        flash('Action non autorisée', 'danger')
        return redirect(url_for('manage_session', session_id=session_id))
    
    try:
        # Supprimer d'abord toutes les réponses associées à ce quiz
        QuizResponse.query.filter_by(quiz_id=quiz_id).delete()
        
        # Ensuite supprimer le quiz
        db.session.delete(quiz)
        db.session.commit()
        
        flash('Quiz supprimé avec succès', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erreur lors de la suppression du quiz: {str(e)}', 'danger')
    
    return redirect(url_for('manage_session', session_id=session_id))
    
    db.session.delete(quiz)
    db.session.commit()
    flash('Quiz supprimé avec succès', 'success')
    return redirect(url_for('manage_session', session_id=session_id))

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
    socketio.emit('new_quiz_response', {
        'session_id': session_id,
        'quiz_id': quiz_id,
        'selected_option': selected_option
    }, room=f'session_{session_id}')
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

# Gestion des événements WebSocket
@socketio.on('connect')
def handle_connect():
    print(f'Client connected: {request.sid}')

@socketio.on('join_session')
def handle_join_session(data):
    session_id = data.get('session_id')
    if session_id:
        join_room(f'session_{session_id}')
        print(f'Client {request.sid} joined session {session_id}')
        
        # Envoyer l'historique des questions
        questions = Question.query.filter_by(session_id=session_id).order_by(Question.timestamp.asc()).all()
        for question in questions:
            emit('new_question', {
                'session_id': session_id,
                'question_id': question.id,
                'question_text': question.question_text,
                'answer_text': question.answer_text,
                'timestamp': question.timestamp.isoformat()
            }, room=request.sid)
        
        # Envoyer l'historique des quizzes
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
    redis_client.rpush(f"session:{session_id}:quiz_responses", f"Q:{quiz_id}|A:{selected_option}")
    emit('new_quiz_response', {
        'session_id': session_id,
        'quiz_id': quiz_id,
        'selected_option': selected_option
    }, room=f'session_{session_id}')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        # Créer l'admin par défaut s'il n'existe pas
        admin_name = os.getenv('ADMIN_NAME')
        admin_email = os.getenv('ADMIN_EMAIL')
        admin_password = os.getenv('ADMIN_PASSWORD')
        
        if admin_name and admin_email and admin_password:
            admin_user = User.query.filter_by(email=admin_email).first()
            if not admin_user:
                hashed_password = generate_password_hash(admin_password)
                admin_user = User(
                    username=admin_name,
                    email=admin_email,
                    password_hash=hashed_password,
                    role='admin'
                )
                db.session.add(admin_user)
                db.session.commit()
                print(f"Admin user {admin_name} created")
        
        try:
            redis_client.ping()
            print("Redis connection successful")
        except Exception as e:
            print(f"Redis connection failed: {str(e)}")
    
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
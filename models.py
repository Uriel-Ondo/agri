from extensions import db
from flask_login import UserMixin
from datetime import datetime
import uuid
from sqlalchemy.orm import validates

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='expert')
    sessions = db.relationship('Session', backref='user', lazy=True)

class Session(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False)
    stream_key = db.Column(db.String(50), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    questions = db.relationship('Question', backref='session', cascade='all, delete-orphan', lazy=True)
    quizzes = db.relationship('Quiz', backref='session', cascade='all, delete-orphan', lazy=True)
    spectators = db.relationship('Spectator', backref='session', lazy=True)

    
    @property
    def is_active(self):
        """Vérifie si la session est actuellement active"""
        now = datetime.utcnow()
        return self.status == 'live' and self.start_time <= now <= self.end_time

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('session.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    answer_text = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

class Quiz(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('session.id'), nullable=False)
    question = db.Column(db.Text, nullable=False)
    options = db.Column(db.JSON, nullable=False)
    correct_answer = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    responses = db.relationship('QuizResponse', backref='quiz', cascade='all, delete-orphan', lazy=True)

    @validates('session_id')
    def validate_session_id(self, key, session_id):
        if session_id is None:
            raise ValueError("session_id cannot be None for a quiz")
        return session_id

class QuizResponse(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quiz.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    device_id = db.Column(db.String(50), nullable=True)
    selected_option = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class Spectator(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('session.id'), nullable=False)
    spectator_id = db.Column(db.String(50), unique=True, nullable=False, default=lambda: f"spectator_{uuid.uuid4().hex[:8]}")
    status = db.Column(db.String(20), nullable=False, default='pending')  # pending, approved, streaming, rejected
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    stream_key = db.Column(db.String(50), unique=True, nullable=False, default=lambda: f"spectator_{uuid.uuid4().hex[:8]}")
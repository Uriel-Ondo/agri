from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_socketio import SocketIO
from flask_restx import Api
from redis import Redis
from flask import Blueprint

# Initialisation des extensions
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
socketio = SocketIO()
redis_client = None

# Configuration de l'API
api_bp = Blueprint('api', __name__, url_prefix='/api')
api = Api(
    app=api_bp,
    version='1.0',
    title='AgriAssist API',
    description='API documentation for AgriAssist streaming platform',
    doc='/apidocs/',
    default='AgriAssist',
    default_label='API endpoints'
)

def init_redis(app):
    global redis_client
    try:
        redis_client = Redis(
            host=app.config['REDIS_HOST'],
            port=app.config['REDIS_PORT'],
            db=app.config['REDIS_DB'],
            socket_connect_timeout=5  # Timeout de connexion
        )
        # Test la connexion
        redis_client.ping()
        print("Connexion Redis établie avec succès")
        return redis_client
    except Exception as e:
        print(f"Erreur de connexion Redis: {str(e)}")
        return None
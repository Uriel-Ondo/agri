from flask import Flask
from config import Config
from extensions import db, migrate, login_manager, socketio, api_bp, init_redis
from app.routes import auth_bp, admin_bp, sessions_bp, quizzes_bp, main_bp
from app.api import namespaces
from app.sockets import register_handlers
from app.models import User

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialiser les extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    
    # Initialiser Redis
    redis_client = init_redis(app)
    
    # Configuration de SocketIO
    socketio.init_app(
        app,
        cors_allowed_origins="*",
        async_mode='gevent',
        logger=True,
        engineio_logger=True,
        ping_timeout=60,
        ping_interval=25
    )
    
    # Enregistrer les blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(sessions_bp)
    app.register_blueprint(quizzes_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)
    
    # Charger les namespaces de l'API
    namespaces.load_namespaces()
    
    # Charger les gestionnaires de sockets
    register_handlers(socketio, redis_client, db)
    
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))
    
    return app, socketio
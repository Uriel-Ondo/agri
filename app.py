import os
from flask import Flask
from config import Config
from extensions import db, migrate, login_manager, socketio, api_bp, init_redis
from models import User
from routes import auth_bp, admin_bp, sessions_bp, quizzes_bp, main_bp
from api import namespaces
import sockets

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
socketio.init_app(app, 
                  cors_allowed_origins="*", 
                  async_mode='gevent',
                  logger=True,
                  engineio_logger=True,
                  ping_timeout=60,
                  ping_interval=25)

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
from sockets import register_handlers
register_handlers(socketio, redis_client, db)
sockets.register_handlers(socketio, redis_client, db)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

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
                from werkzeug.security import generate_password_hash
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
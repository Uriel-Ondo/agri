import os
from app import create_app
from extensions import db, migrate
from app.models import User
from werkzeug.security import generate_password_hash

app, socketio = create_app()

if __name__ == '__main__':
    with app.app_context():
        # Appliquer les migrations pour créer/mettre à jour les tables
        try:
            migrate.init_app(app, db)
            db.session.execute("SELECT 1")  # Test de connexion à la base
            from flask_migrate import upgrade
            upgrade()  # Applique les migrations existantes
            print("Database tables created/updated via migrations")
        except Exception as e:
            print(f"Error during database migration: {str(e)}")
            db.create_all()  # Fallback vers create_all si la migration échoue
            print("Fallback: Database tables created with db.create_all()")

        # Créer l'admin par défaut s'il n'existe pas
        admin_name = os.getenv('ADMIN_NAME')
        admin_email = os.getenv('ADMIN_EMAIL')
        admin_password = os.getenv('ADMIN_PASSWORD')

        if admin_name and admin_email and admin_password:
            admin_user = db.session.query(User).filter_by(email=admin_email).first()
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

    socketio.run(app, debug=True, host='0.0.0.0', port=5001)
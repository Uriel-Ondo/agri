Agri-Assist
Agri-Assist est une application web interactive conçue pour fournir des informations agricoles via des sessions de streaming vidéo en direct (RTMP/HLS), des quiz interactifs, et une fonctionnalité de questions/réponses en temps réel. L'application est construite avec Flask, utilise MySQL pour la base de données, Redis pour la gestion des sessions et des sockets, et réutilise le serveur SRS (Simple Realtime Server) de Dr_sante pour le streaming vidéo.
Fonctionnalités

Streaming vidéo : Diffusion en direct via RTMP (entrée) et HLS (lecture) avec SRS.
Quiz interactifs : Les utilisateurs peuvent répondre à des quiz agricoles affichés pendant les sessions en direct.
Questions/Réponses : Les utilisateurs peuvent poser des questions via une interface web, avec des réponses en temps réel via SocketIO.
Administration : Interface d'administration pour gérer les sessions, quiz, et réponses.

Prérequis

Docker : Version 20.10 ou supérieure.
Docker Compose : Version 2.0 ou supérieure.
Git : Pour cloner le dépôt.
OBS Studio (optionnel) : Pour tester la publication de flux RTMP.
VLC Media Player (optionnel) : Pour tester les flux HLS.
Serveur SRS : Le projet réutilise le SRS de Dr_sante (ports 1935, 8080 sur 63.250.58.55).
DNS : agri.visiotech.me et www.agri.visiotech.me doivent pointer vers 63.250.58.55.

Structure du projet
agri/
├── app.py                  # Application Flask principale
├── config.py              # Configuration Flask
├── entrypoint.sh          # Script d'entrée pour le conteneur web
├── Dockerfile             # Définition du conteneur Flask
├── docker-compose.yml     # Configuration des services Docker
├── .env.docker            # Variables d'environnement (non versionnées)
├── media/                 # Dossier pour les fichiers HLS (généré)
├── routes/                # Blueprints Flask
├── models/                # Modèles SQLAlchemy
├── static/                # Fichiers statiques (CSS, JS)
├── templates/             # Templates HTML (ex. hbbtv_index.html)
├── requirements.txt       # Dépendances Python
└── README.md              # Ce fichier

Configuration
1. Cloner le dépôt
cd /home/uriel/projets
git clone git@github.com:nospi510/agri.git
cd agri

2. Créer le fichier .env.docker
Créez un fichier .env.docker à la racine du projet avec le contenu suivant :
SECRET_KEY=$(openssl rand -hex 24)
FLASK_DEBUG=0

# Database
SQLALCHEMY_DATABASE_URI=mysql+mysqldb://admin:Passer123!@db/agri_assist
MYSQL_ROOT_PASSWORD=rootpassword
MYSQL_DATABASE=agri_assist
MYSQL_USER=admin
MYSQL_PASSWORD=password

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

# SRS Configuration
SRS_SERVER=ip_du_server
SRS_RTMP_PORT=1935
SRS_HTTP_PORT=8080
PUBLIC_DOMAIN=agri.visiotech.me

# Admin
ADMIN_NAME=admin
ADMIN_EMAIL=admin@mail.test
ADMIN_PASSWORD=password

Notes :

Ne versionnez pas .env.docker (exclu par .gitignore).
Assurez-vous que Dr_sante est en cours d’exécution pour accéder à SRS.

3. Configurer Nginx
Mettez à jour /home/nospi/projets/visiotech/nginx/conf.d/app.conf pour ajouter agri.visiotech.me :
nano /home/nospi/projets/visiotech/nginx/conf.d/app.conf

Ajoutez un bloc pour agri.visiotech.me (voir ci-dessous).
4. Construire et lancer les conteneurs
cd /home/uriel/projets/agri
docker compose up --build -d

Cela démarre les services suivants :

web : Application Flask (port 8004).
db : Base de données MySQL (port interne 3306).
redis : Cache Redis (port interne 6379).

5. Initialiser la base de données
docker compose exec web flask db init
docker compose exec web flask db migrate -m "Initial deployment"
docker compose exec web flask db upgrade

6. Créer l’utilisateur admin
docker compose exec web python -c "from app import create_app; app=create_app(); with app.app_context(): from models import User; from werkzeug.security import generate_password_hash; u=User(username='uriel', email='uriel@visiotech.me', password_hash=generate_password_hash('Passer123!'), role='admin'); from extensions import db; db.session.add(u); db.session.commit()"

7. Configurer HTTPS
Générez les certificats SSL pour agri.visiotech.me :
cd /home/nospi/projets/visiotech
docker compose exec certbot certbot certonly --webroot --webroot-path=/etc/letsencrypt -d agri.visiotech.me -d www.agri.visiotech.me

Redémarrez Nginx :
docker compose restart nginx

Test en local

Exposer le port 8004 :Dans docker-compose.yml, le port 8004 est déjà exposé. Accédez à :

Localement : http://localhost:8004
Depuis une autre machine : http://63.250.58.55:8004


Vérifier WebSocket :Ouvre la console du navigateur (F12) et confirme WebSocket connected.

Tester la diffusion :

Configurez OBS avec l’URL RTMP : rtmp://63.250.58.55:1935/live/session_<stream_key>
Testez l’URL HLS dans VLC : http://63.250.58.55:8080/live/session_<stream_key>.m3u8
Accédez à http://63.250.58.55:8004/hbbtv et vérifiez le flux vidéo.



Test en production

Désactiver le port local :Dans docker-compose.yml, commentez :
#ports:
#  - "8004:8004"


Redémarrer :
docker compose up -d


Accéder :

URL : https://agri.visiotech.me
WebSocket : wss://agri.visiotech.me/socket.io
HLS : https://agri.visiotech.me/live/session_<stream_key>.m3u8


Vérifier la diffusion :

Configurez OBS avec l’URL RTMP : rtmp://63.250.58.55:1935/live/session_<stream_key>
Testez l’URL HLS dans un navigateur ou VLC : https://agri.visiotech.me/live/session_<stream_key>.m3u8



Dépannage
Vérifier les journaux
docker compose logs web
docker compose logs db
docker compose logs redis
docker logs dr_sante-srs-1
cat /home/nospi/projets/visiotech/nginx/logs/error.log

Vérifier SRS
docker logs dr_sante-srs-1
curl http://63.250.58.55:8080

Vérifier Redis
docker compose exec redis redis-cli ping

Vérifier les tables
docker compose exec db mysql -uadmin -pPasser123! -e "USE agri_assist; SHOW TABLES;"

Vérifier l’utilisateur admin
docker compose exec db mysql -uadmin -pPasser123! -e "USE agri_assist; SELECT * FROM user WHERE email='uriel@visiotech.me';"

Vérifier WebSocket

Ouvre la console du navigateur (F12) et vérifie la connexion à ws://63.250.58.55:8004/socket.io (local) ou wss://agri.visiotech.me/socket.io (production).
Cherche WebSocket connected.

Vérifier la diffusion

Si le flux HLS ne charge pas dans hbbtv_index.html, testez :vlc http://63.250.58.55:8080/live/session_<stream_key>.m3u8


Vérifiez les journaux SRS :docker logs dr_sante-srs-1



Notes

SRS : Réutilise le SRS de Dr_sante (rtmp://63.250.58.55:1935/live/session_<stream_key>, http://63.250.58.55:8080/live/session_<stream_key>.m3u8). En production, HLS passe par Nginx (https://agri.visiotech.me/live/...).
WebSocket : Assurez-vous que gevent-websocket est dans requirements.txt.
Sécurité : Les mots de passe dans .env.docker sont sensibles et non versionnés.
Nginx : Configuré dans /home/nospi/projets/visiotech.

Contributeurs

Uriel (uriel@visiotech.me)

Licence
Ce projet est sous licence MIT. Voir le fichier LICENSE pour plus de détails.
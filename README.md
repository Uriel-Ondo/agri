# Agri-Assist

Agri-Assist est une application web interactive conçue pour fournir des informations agricoles via des sessions de streaming vidéo en direct (RTMP/HLS), des quiz interactifs, et une fonctionnalité de questions/réponses en temps réel. L'application est construite avec Flask, utilise MySQL pour la base de données, Redis pour la gestion des sessions et des sockets, et SRS (Simple Realtime Server) pour le streaming vidéo.

## Fonctionnalités
- **Streaming vidéo** : Diffusion en direct via RTMP (entrée) et HLS (lecture) avec SRS.
- **Quiz interactifs** : Les utilisateurs peuvent répondre à des quiz agricoles affichés pendant les sessions en direct.
- **Questions/Réponses** : Les utilisateurs peuvent poser des questions via une interface web, avec des réponses en temps réel via SocketIO.
- **Administration** : Interface d'administration pour gérer les sessions, quiz, et réponses.

## Prérequis
- **Docker** : Version 20.10 ou supérieure.
- **Docker Compose** : Version 2.0 ou supérieure.
- **Git** : Pour cloner le dépôt.
- **OBS Studio** (optionnel) : Pour tester la publication de flux RTMP.
- **VLC Media Player** (optionnel) : Pour tester les flux HLS.

## Arborescence du projet

```text
agri/
├── Dockerfile
├── README.md
├── api
│   ├── __init__.py
│   └── namespaces.py
├── app.py
├── config.py
├── docker-compose.yml
├── entrypoint.sh
├── extensions.py
├── models.py
├── requirements.txt
├── routes
│   ├── __init__.py
│   ├── admin.py
│   ├── auth.py
│   ├── main.py
│   ├── quizzes.py
│   └── sessions.py
├── sockets.py
├── srs
│   └── srs.conf
├── static
│   ├── css
│   │   ├── style.css
│   │   └── styles.css
│   └── images
│       └── favicon.ico
└── templates
    ├── admin_create_user.html
    ├── admin_dashboard.html
    ├── admin_edit_user.html
    ├── base.html
    ├── broadcast.html
    ├── create_quiz.html
    ├── create_session.html
    ├── dashboard.html
    ├── hbbtv_index.html
    ├── live_session.html
    ├── login.html
    ├── manage_session.html
    ├── profile.html
    ├── quiz_results.html
    └── register.html
```

## Configuration

### 1. Cloner le dépôt
```bash
git clone <URL_DU_DÉPÔT>
cd agri
```
### 2. Créer le fichier .env.docker
Créez un fichier .env.docker à la racine du projet avec le contenu suivant :

```bash
# Application
SECRET_KEY="votre_clé_secrète_sécurisée"
FLASK_DEBUG=0

# Database
SQLALCHEMY_DATABASE_URI="mysql+mysqldb://admin:Passer123!@db/agri_assist"
MYSQL_PASSWORD="Passer123!"

# Redis
REDIS_HOST="redis"
REDIS_PORT=6379
REDIS_DB=0

# SRS Configuration
SRS_SERVER="localhost"
SRS_RTMP_PORT=1935
SRS_HTTP_PORT=8080
HOST_IP="votre_ip_hôte"  # Ex. 192.168.1.99

# Admin
ADMIN_NAME="admin"
ADMIN_EMAIL="admin@example.com"
ADMIN_PASSWORD="votre_mot_de_passe_admin"

# Stream Configuration
STREAM_KEY="livestream"
HLS_PLAYLIST="live/livestream.m3u8"

```

## Notes :

Remplacez votre_clé_secrète_sécurisée par une clé générée (par exemple, openssl rand -hex 32).
Remplacez HOST_IP par l'IP de votre machine hôte (exécutez ip addr pour la trouver).
Ne versionnez pas .env.docker (il est exclu par .gitignore).

### 3. Construire et lancer les conteneurs
```bash
docker-compose up --build -d
```

Cela démarre les services suivants :

web : Application Flask (port 5000 pour l'interface, 9999 pour SocketIO).
db : Base de données MySQL (port interne 3306).
redis : Cache Redis (port interne 6379).
srs : Serveur SRS pour le streaming RTMP/HLS (ports 1935, 8080, 1985, 8000/udp).

### 4. Vérifier les logs
```bash
docker-compose logs -f web
docker-compose logs -f srs
docker-compose logs -f db
docker-compose logs -f redis
```

### 5. Tester le streaming

Publier un flux RTMP :

Utilisez OBS Studio :
URL : rtmp://localhost:1935/live/livestream
Clé de flux : livestream (ou la valeur de STREAM_KEY dans .env.docker).


### Vérifiez les logs SRS :
```bash
docker-compose logs -f srs
```



Lire le flux HLS :

Ouvrez http://localhost:8080/live/livestream.m3u8 dans VLC ou un navigateur.
Accédez à http://localhost:5000 pour voir le flux dans l'interface web.


Vérifier CORS :
curl -I http://localhost:8080/live/livestream.m3u8

Vérifiez la présence de Access-Control-Allow-Origin: *.


### 6. Accéder à l'interface d'administration

URL : http://localhost:5000/admin
Identifiants : Utilisez ADMIN_EMAIL et ADMIN_PASSWORD définis dans .env.docker.

Dépannage

Conteneur web unhealthy :
Vérifiez les logs : docker-compose logs -f web.
Testez l'endpoint de santé : docker-compose exec web curl http://localhost:5000/health-check.
Assurez-vous que entrypoint.sh attend les services (db, redis, srs).


Erreur CORS :
Vérifiez que srs.conf inclut les en-têtes CORS dans http_server.http_headers.
Testez avec curl -I http://localhost:8080/live/livestream.m3u8.


Connexion à la base de données échoue :
Testez : docker-compose exec web mysql -h db -u admin -pPasser123! -e "SELECT 1".


Redis non accessible :
Testez : docker-compose exec web redis-cli -h redis ping.


### SRS ne diffuse pas :
Vérifiez les logs : 
```bash
docker-compose logs -f srs
```

Testez l'API :
```bash
 docker-compose exec web curl http://srs:1985/api/v1/versions.
```


### Maintenance

Mettre à jour les dépendances :
```bash
docker-compose down
docker-compose build
docker-compose up -d
```

### Nettoyer les volumes :
```bash
docker-compose down --volumes
```
Attention : Cela supprime toutes les données persistantes (base de données, Redis, médias).

## Structure des services



Service
Description
Ports


web
Application Flask (interface web et SocketIO)
5000, 9999


db
Base de données MySQL
3306 (interne)


redis
Cache Redis pour sessions et sockets
6379 (interne)


srs
Serveur SRS pour streaming RTMP/HLS
1935 (RTMP), 8080 (HLS), 1985 (API), 8000/udp (WebRTC)

Initialiser la base de donne
docker-compose exec web flask db init
 docker-compose exec web flask db migrate
docker-compose exec web flask db upgrade


### Contributeurs

Uriel (uriel@visiotech.me)

### Licence
Ce projet est sous licence MIT. Voir le fichier LICENSE pour plus de détails.```
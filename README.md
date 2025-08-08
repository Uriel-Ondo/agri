# Agri-Assist

Agri-Assist est une application web interactive conçue pour fournir des informations agricoles via des sessions de streaming vidéo en direct (RTMP/HLS), des quiz interactifs, et une fonctionnalité de questions/réponses en temps réel. L'application est construite avec Flask, utilise MySQL pour la base de données, Redis pour la gestion des sessions et des sockets, et réutilise le serveur SRS (Simple Realtime Server) de `Dr_sante` pour le streaming vidéo.

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
- **Serveur SRS** : Le projet réutilise le SRS de `Dr_sante` (ports 1935, 8080 sur `63.250.58.55`).
- **DNS** : `agri.visiotech.me` et `www.agri.visiotech.me` doivent pointer vers `63.250.58.55`.

## Structure du projet

```
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
```

## Configuration

### 1. Cloner le dépôt
```bash
cd /home/uriel/projets
git clone git@github.com:nospi510/agri.git
cd agri
```

### 2. Créer le fichier `.env.docker`
Créez un fichier `.env.docker` à la racine du projet avec le contenu suivant :

```env
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
SRS_SERVER=63.x.x.x
SRS_RTMP_PORT=1935
SRS_HTTP_PORT=8080
PUBLIC_DOMAIN=agri.visiotech.me

# Admin
ADMIN_NAME=admin
ADMIN_EMAIL=admin@test.me
ADMIN_PASSWORD=Password
```

**Notes** :
- Ne versionnez pas `.env.docker` (exclu par `.gitignore`).
- Assurez-vous que `Dr_sante` est en cours d’exécution pour accéder à SRS.

### 3. Configurer Nginx
Mettez à jour `/home/nospi/projets/visiotech/nginx/conf.d/app.conf` pour ajouter `agri.visiotech.me` :

```bash
nano /home/nospi/projets/visiotech/nginx/conf.d/app.conf
```

Ajoutez un bloc pour `agri.visiotech.me` (voir ci-dessous).

### 4. Construire et lancer les conteneurs
```bash
cd /home/uriel/projets/agri
docker compose up --build -d
```

Cela démarre les services suivants :
- `web` : Application Flask (port 8004).
- `db` : Base de données MySQL (port interne 3306).
- `redis` : Cache Redis (port interne 6379).

### 5. Initialiser la base de données
```bash
docker compose exec web flask db init
docker compose exec web flask db migrate -m "Initial deployment"
docker compose exec web flask db upgrade
```

### 6. Créer l’utilisateur admin
```bash
docker compose exec web python -c "from app import create_app; app=create_app(); with app.app_context(): from models import User; from werkzeug.security import generate_password_hash; u=User(username='uriel', email='uriel@visiotech.me', password_hash=generate_password_hash('Passer123!'), role='admin'); from extensions import db; db.session.add(u); db.session.commit()"
```

### 7. Configurer HTTPS
Générez les certificats SSL pour `agri.visiotech.me` :
```bash
cd /home/nospi/projets/visiotech
docker compose exec certbot certbot certonly --webroot --webroot-path=/etc/letsencrypt -d agri.visiotech.me -d www.agri.visiotech.me
```

Redémarrez Nginx :
```bash
docker compose restart nginx
```

## Test en local

1. **Exposer le port 8004** :
   Dans `docker-compose.yml`, le port 8004 est déjà exposé. Accédez à :
   - Localement : `http://localhost:8004`
   - Depuis une autre machine : `http://63.250.58.55:8004`

2. **Vérifier WebSocket** :
   Ouvre la console du navigateur (F12) et confirme `WebSocket connected`.

3. **Tester la diffusion** :
   - Configurez OBS avec l’URL RTMP : `rtmp://63.250.58.55:1935/live/session_<stream_key>`
   - Testez l’URL HLS dans VLC : `http://63.250.58.55:8080/live/session_<stream_key>.m3u8`
   - Accédez à `http://63.250.58.55:8004/hbbtv` et vérifiez le flux vidéo.

## Test en production

1. **Désactiver le port local** :
   Dans `docker-compose.yml`, commentez :
   ```yaml
   #ports:
   #  - "8004:8004"
   ```

2. **Redémarrer** :
   ```bash
   docker compose up -d
   ```

3. **Accéder** :
   - URL : `https://agri.visiotech.me`
   - WebSocket : `wss://agri.visiotech.me/socket.io`
   - HLS : `https://agri.visiotech.me/live/session_<stream_key>.m3u8`

4. **Vérifier la diffusion** :
   - Configurez OBS avec l’URL RTMP : `rtmp://63.250.58.55:1935/live/session_<stream_key>`
   - Testez l’URL HLS dans un navigateur ou VLC : `https://agri.visiotech.me/live/session_<stream_key>.m3u8`

## Dépannage

### Vérifier les journaux
```bash
docker compose logs web
docker compose logs db
docker compose logs redis
docker logs dr_sante-srs-1
cat /home/nospi/projets/visiotech/nginx/logs/error.log
```

### Vérifier SRS
```bash
docker logs dr_sante-srs-1
curl http://63.250.58.55:8080
```

### Vérifier Redis
```bash
docker compose exec redis redis-cli ping
```

### Vérifier les tables
```bash
docker compose exec db mysql -uadmin -pPasser123! -e "USE agri_assist; SHOW TABLES;"
```

### Vérifier l’utilisateur admin
```bash
docker compose exec db mysql -uadmin -pPasser123! -e "USE agri_assist; SELECT * FROM user WHERE email='uriel@visiotech.me';"
```

### Vérifier WebSocket
- Ouvre la console du navigateur (F12) et vérifie la connexion à `ws://63.250.58.55:8004/socket.io` (local) ou `wss://agri.visiotech.me/socket.io` (production).
- Cherche `WebSocket connected`.

### Vérifier la diffusion
- Si le flux HLS ne charge pas dans `hbbtv_index.html`, testez :
  ```bash
  vlc http://63.250.58.55:8080/live/session_<stream_key>.m3u8
  ```
- Vérifiez les journaux SRS :
  ```bash
  docker logs dr_sante-srs-1
  ```

## Notes
- **SRS** : Réutilise le SRS de `Dr_sante` (`rtmp://63.250.58.55:1935/live/session_<stream_key>`, `http://63.250.58.55:8080/live/session_<stream_key>.m3u8`). En production, HLS passe par Nginx (`https://agri.visiotech.me/live/...`).
- **WebSocket** : Assurez-vous que `gevent-websocket` est dans `requirements.txt`.
- **Sécurité** : Les mots de passe dans `.env.docker` sont sensibles et non versionnés.
- **Nginx** : Configuré dans `/home/nospi/projets/visiotech`.

## Contributeurs
- Uriel (uriel@visiotech.me)

## Licence
Ce projet est sous licence MIT. Voir le fichier `LICENSE` pour plus de détails.

</xaiArtifact>

**Changements** :
- Supprimé les références à `localhost` et au service SRS local.
- Ajouté la réutilisation du SRS de `Dr_sante`.
- Mis à jour les ports (5000 → 8004).
- Ajouté les instructions pour configurer Nginx et HTTPS.
- Simplifié les sections inutiles (CORS, volumes de SRS).

### Étape 3 : Configurer Nginx
On met à jour `/home/nospi/projets/visiotech/nginx/conf.d/app.conf` pour ajouter `agri.visiotech.me`.

<xaiArtifact artifact_id="2ac14523-e43d-4e4f-b4a6-e6484e73ee83" artifact_version_id="3cff252f-466f-42ca-afac-075e8d662145" title="app.conf" contentType="text/nginx">

server {
    listen 443 ssl;
    server_name drsante.visiotech.me www.drsante.visiotech.me;

    ssl_certificate /etc/letsencrypt/live/drsante.visiotech.me/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/drsante.visiotech.me/privkey.pem;

    location / {
        proxy_pass http://dr_sante-web-1:8003;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /socket.io {
        proxy_pass http://dr_sante-web-1:8003;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /live {
        proxy_pass http://dr_sante-srs-1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 10s;
        proxy_read_timeout 30s;
        proxy_send_timeout 30s;
    }
}

server {
    listen 443 ssl;
    server_name agri.visiotech.me www.agri.visiotech.me;

    ssl_certificate /etc/letsencrypt/live/agri.visiotech.me/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/agri.visiotech.me/privkey.pem;

    location / {
        proxy_pass http://agri-web-1:8004;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /socket.io {
        proxy_pass http://agri-web-1:8004;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /live {
        proxy_pass http://dr_sante-srs-1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 10s;
        proxy_read_timeout 30s;
        proxy_send_timeout 30s;
    }
}

server {
    listen 80;
    server_name drsante.visiotech.me www.drsante.visiotech.me agri.visiotech.me www.agri.visiotech.me;
    return 301 https://$host$request_uri;
}

</xaiArtifact>

**Changements** :
- Ajouté un bloc `server` pour `agri.visiotech.me` pointant vers `agri-web-1:8004`.
- Configuré `/live` pour utiliser `dr_sante-srs-1:8080`.
- Mis à jour le bloc HTTP pour inclure `agri.visiotech.me`.

### Étape 4 : Hébergement et tests
1. **Valider les changements Git** :
   ```bash
   cd /home/uriel/projets/agri
   git add Dockerfile docker-compose.yml .env.docker entrypoint.sh config.py routes/sessions.py api/namespaces.py app.py README.md
   git commit -m "Adaptation pour déploiement sur agri.visiotech.me avec SRS de Dr_sante"
   git push origin deploiement
   ```

2. **Vérifier le réseau Docker** :
   Assure-toi que `dr_sante_app-network` existe :
   ```bash
   docker network ls
   ```
   Vérifie que `visiotech-nginx-1` est connecté :
   ```bash
   docker network inspect dr_sante_app-network
   ```
   Sinon, reconnecte :
   ```bash
   docker network connect dr_sante_app-network visiotech-nginx-1
   ```

3. **Construire et lancer les conteneurs** :
   ```bash
   cd /home/uriel/projets/agri
   docker compose up --build -d
   ```

4. **Initialiser la base de données** :
   ```bash
   docker compose exec web flask db init
   docker compose exec web flask db migrate -m "Initial deployment"
   docker compose exec web flask db upgrade
   ```

5. **Créer l’utilisateur admin** :
   ```bash
   docker compose exec web python -c "from app import create_app; app=create_app(); with app.app_context(): from models import User; from werkzeug.security import generate_password_hash; u=User(username='uriel', email='uriel@visiotech.me', password_hash=generate_password_hash('Passer123!'), role='admin'); from extensions import db; db.session.add(u); db.session.commit()"
   ```

6. **Configurer HTTPS** :
   ```bash
   cd /home/nospi/projets/visiotech
   docker compose exec certbot certbot certonly --webroot --webroot-path=/etc/letsencrypt -d agri.visiotech.me -d www.agri.visiotech.me
   docker compose restart nginx
   ```

7. **Tester en local** :
   - Accède à `http://63.250.58.55:8004` pour vérifier l’interface.
   - Teste WebSocket dans la console du navigateur.
   - Configure OBS avec `rtmp://63.250.58.55:1935/live/session_<stream_key>`.
   - Ouvre `http://63.250.58.55:8080/live/session_<stream_key>.m3u8` dans VLC.

8. **Tester en production** :
   - Commente le port 8004 dans `docker-compose.yml` :
     ```yaml
     #ports:
     #  - "8004:8004"
     ```
   - Redémarre :
     ```bash
     cd /home/uriel/projets/agri
     docker compose up -d
     ```
   - Accède à `https://agri.visiotech.me`.
   - Teste `https://agri.visiotech.me/live/session_<stream_key>.m3u8` dans un navigateur ou VLC.
   - Vérifie WebSocket à `wss://agri.visiotech.me/socket.io`.

9. **Vérifier les logs** :
   ```bash
   cd /home/uriel/projets/agri
   docker compose logs web
   docker compose logs db
   docker compose logs redis
   docker logs dr_sante-srs-1
   cat /home/nospi/projets/visiotech/nginx/logs/error.log
   ```

# Agri-Assist

Agri-Assist est une plateforme innovante qui utilise la télévision numérique terrestre (TNT) interactive pour diffuser des connaissances agricoles aux agriculteurs au Sénégal, en particulier dans les zones rurales à faible connectivité Internet. La plateforme permet des sessions en direct avec des experts agricoles, la soumission de questions en temps réel et des quiz interactifs via des téléviseurs compatibles HbbTV, favorisant un apprentissage actif et l'amélioration des pratiques agricoles.

---

## Table des matières

- [Présentation](#présentation)
- [Fonctionnalités](#fonctionnalités)
- [Architecture](#architecture)
- [Technologies](#technologies)
- [Installation](#installation)
- [Utilisation](#utilisation)
- [Tests](#tests)
- [Défis et solutions](#défis-et-solutions)
- [Améliorations futures](#améliorations-futures)
- [Licence](#licence)
- [Contact](#contact)

---

## Présentation

Agri-Assist répond au défi de la diffusion des connaissances agricoles dans les zones rurales du Sénégal, où 55 % de la population réside et où l'accès à Internet est limité. En exploitant la couverture étendue de la TNT et l'interactivité de HbbTV, la plateforme propose des contenus éducatifs, permet des interactions en temps réel avec des experts et soutient les agriculteurs dans l'adoption de pratiques agricoles modernes et durables.

---

## Fonctionnalités

- **Diffusion en direct** : Les experts agricoles diffusent des sessions en direct via la TNT en utilisant l'ingestion RTMP et la sortie HLS.
- **Interaction en temps réel** : Les agriculteurs peuvent soumettre des questions et participer à des quiz via leurs téléviseurs compatibles HbbTV en utilisant WebSocket.
- **Interface conviviale** : Interface web pour les experts (basée sur Flask) et interface TV pour les agriculteurs (HbbTV) avec prise en charge du français et du wolof.
- **Gestion des données** : Stockage persistant avec MySQL pour les profils utilisateurs, les sessions et les questions ; gestion des données en temps réel avec Redis Streams.
- **Scalabilité** : Prend en charge jusqu'à 100 utilisateurs simultanés avec une latence minimale (200 ms pour les interactions WebSocket).

---

## Architecture

La plateforme comprend les composants suivants :

- **Application web (Flask)** : Permet aux experts de gérer leurs profils, planifier des sessions et répondre aux questions.
- **Base de données (MySQL)** : Stocke les données des utilisateurs, les détails des sessions, les questions et les réponses aux quiz.
- **Serveur de streaming (SRS)** : Gère l'ingestion RTMP des experts et transcodage en HLS/MPEG-TS pour la diffusion TNT.
- **Données en temps réel (Redis)** : Gère les interactions en direct (questions, quiz) via Redis Streams.
- **Application HbbTV** : Permet aux agriculteurs d'accéder aux sessions en direct et d'interagir via leur télécommande.
- **Infrastructure TNT** : Distribue les flux vidéo et les applications HbbTV à l'échelle nationale, gérée par TDS-SA.


---

## Technologies

- **Backend** : Flask (Python) pour l'application web
- **Base de données** : MySQL pour le stockage persistant, Redis pour les données en temps réel
- **Streaming** : Simple Realtime Server (SRS) pour RTMP et HLS/MPEG-TS
- **Frontend** : HbbTV (HTML, CSS, JavaScript) pour l'interactivité sur TV
- **Protocoles** : RTMP, HLS, WebSocket pour le streaming et la communication en temps réel
- **Infrastructure** : TNT avec la norme DVB-T2, gérée par TDS-SA

---

## Installation

### Prérequis

- Ubuntu 20.04 ou ultérieur (ou distribution Linux équivalente)
- Python 3.8+
- MySQL 8.0+
- Redis 6.0+
- SRS (Simple Realtime Server) 4.0+
- Nginx (pour servir les applications Flask et HbbTV)
- Téléviseurs ou décodeurs compatibles HbbTV

### Étapes

#### 1. Cloner le dépôt

```bash
git clone https://github.com/Uriel-Ondo/agri.git
cd agri
```

#### 2. Installer les dépendances

```bash
# Installer les dépendances Python
pip install -r requirements.txt

# Installer MySQL
sudo apt-get install mysql-server
sudo mysql_secure_installation

# Installer Redis
sudo apt-get install redis-server

# Installer SRS
git clone https://github.com/ossrs/srs.git
cd srs
./configure && make
sudo make install
```

#### 3. Configurer MySQL

Créer la base de données et les tables :
```sql
mysql -u root -p
CREATE DATABASE agri_assist;
USE agri_assist;
source database/schema.sql;
```

#### 4. Configurer SRS

Modifier le fichier de configuration SRS (`/usr/local/srs/conf/srs.conf`) :

```
# main config for srs.
# @see full.conf for detail config.

listen              1935;
max_connections     1000;
#srs_log_tank        file;
#srs_log_file        ./objs/srs.log;
daemon              on;
http_api {
    enabled         on;
    listen          1985;
}
http_server {
    enabled         on;
    listen          8080;
    dir             ./objs/nginx/html;
}
rtc_server {
    enabled on;
    listen 8000; # UDP port
    # @see https://ossrs.net/lts/zh-cn/docs/v4/doc/webrtc#config-candidate
    candidate $CANDIDATE;
}
vhost __defaultVhost__ {
	enabled         on;
	chunk_size      4000;
	
	http {
        enabled     on;
        
    }
    hls {
        enabled         on;
	hls_path	./objs/nginx/html/live;
	hls_fragment	1;
	hls_window	30;
	hls_cleanup	off;
	hls_m3u8_file  [stream].m3u8;  
        hls_ts_file     [stream]-[seq].ts; 
    }
    http_remux {
        enabled     on;
        mount       [vhost]/[app]/[stream].flv;
    }
    rtc {
        enabled     on;
        # @see https://ossrs.net/lts/zh-cn/docs/v4/doc/webrtc#rtmp-to-rtc
        rtmp_to_rtc off;
        # @see https://ossrs.net/lts/zh-cn/docs/v4/doc/webrtc#rtc-to-rtmp
        rtc_to_rtmp on;
	bframe	    discard;
    }

    play{
        gop_cache_max_frames 2500;
    }
}
```

#### 5. Configurer Flask

Définir les variables d'environnement dans `.env` :

```
SECRET_KEY="votre_clef_secrete"
SQLALCHEMY_DATABASE_URI="mysql://urser:password@localhost/agri_assist"
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
SRS_SERVER=localhost
SRS_RTMP_PORT=1935
SRS_HTTP_PORT=8080
ADMIN_NAME="name"
ADMIN_EMAIL="mail"
ADMIN_PASSWORD="password"
```

#### 6. Lancer l'application

```bash
# Démarrer Redis
sudo systemctl start redis

# Démarrer SRS
/usr/local/srs/objs/srs -c /usr/local/srs/conf/srs.conf

# Démarrer Flask
flask run
```

---

## Utilisation

- **Pour les experts** : Connectez-vous à l'interface web pour planifier et animer des sessions, répondre aux questions et consulter les statistiques.
- **Pour les agriculteurs** : Accédez à la chaîne TNT dédiée via un téléviseur ou décodeur compatible HbbTV, participez en direct et interagissez avec les experts via la télécommande.

---

## Tests

- Tester la latence et la robustesse des interactions en conditions réelles (multi-utilisateurs).

---

## Défis et solutions

- **Connectivité limitée** : Utilisation de la TNT et du standard HbbTV pour contourner la dépendance à Internet.
- **Interaction temps réel** : Intégration de Redis Streams et WebSocket pour assurer des latences minimales.
- **Multilinguisme** : Prise en charge du français et du wolof dès la première version.

---

## Améliorations futures

- **Intégration mobile** : Développer une application mobile complémentaire pour les utilisateurs de smartphones.
- **Accès hors ligne** : Permettre le téléchargement de contenus pour une visualisation hors connexion sur des décodeurs avec stockage.
- **Personnalisation par IA** : Utiliser l'IA pour adapter le contenu en fonction de la région ou du type de culture.
- **Support multilingue** : Ajouter des langues comme le peul et le sérère.
- **Expansion sectorielle** : Étendre à l'éducation et à la santé.

---

## Licence

Ce projet est sous licence MIT. Consultez le fichier [LICENSE](LICENSE) pour plus de détails.

---

## Contact

Pour toute question, contactez l'équipe du projet à :

- **Email** : uriel@visiotech.me
- **GitHub** : [Uriel-Ondo/agri](https://github.com/Uriel-Ondo/agri.git)

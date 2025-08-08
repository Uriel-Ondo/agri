#!/bin/bash
set -e

echo "Step 0: Initial delay for services initialization..."
sleep 15

# Fonction améliorée avec timeout et vérification active
wait_for_service() {
    local host=$1
    local port=$2
    local service=$3
    local max_retries=30
    local retries=0

    echo "Step 1: Waiting for $service ($host:$port)..."
    until nc -z -w 1 $host $port; do
        retries=$((retries+1))
        if [ $retries -ge $max_retries ]; then
            echo "Error: $service not available after $max_retries attempts"
            exit 1
        fi
        sleep 2
    done
    echo "$service is ready!"
}

# Attente des services
wait_for_service db 3306 "MySQL"
wait_for_service redis 6379 "Redis"

# Vérification MySQL avec credentials
echo "Step 2: Verifying MySQL database access..."
while ! mysql -h db -u "${MYSQL_USER}" -p"${MYSQL_PASSWORD}" -e "USE agri_assist; SELECT 1;"; do
    echo "MySQL access failed, retrying..."
    sleep 2
done
echo "MySQL access confirmed!"

# Initialisation complète de la base de données
echo "Step 3: Initializing database migrations..."
if [ ! -d "migrations" ]; then
    echo "Creating new migrations repository..."
    flask db init
fi

echo "Generating database migrations..."
flask db migrate -m "Initial deployment"

echo "Applying database migrations..."
for i in {1..3}; do
    flask db upgrade && break || {
        echo "Migration attempt $i failed"
        [ $i -eq 3 ] && exit 1
        sleep 5
    }
done
echo "Database migrations applied successfully!"

# Préparation des répertoires
echo "Step 4: Preparing media directories..."
mkdir -p media/live media/vod
chmod -R 755 media
echo "Media directories prepared!"

# Vérification finale
echo "Step 5: Starting application..."
exec "$@"
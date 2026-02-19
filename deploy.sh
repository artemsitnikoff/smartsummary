#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "=== Pulling latest code..."
git pull

echo "=== Rebuilding and restarting..."
docker compose up -d --build

echo "=== Done. Logs:"
docker compose logs -f --tail=20

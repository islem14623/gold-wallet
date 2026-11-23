#!/usr/bin/env bash
set -euo pipefail

TAG=${1:?Usage: ./deploy.sh <commit-sha>}
SERVER=ubuntu@10.97.0.18
KEY=~/.ssh/gold-server

scp -i "$KEY" docker-compose.prod.yml "$SERVER":~/gold-wallet/docker-compose.yml
ssh -i "$KEY" "$SERVER" "
  cd ~/gold-wallet &&
  sed -i '/^TAG=/d' .env &&
  echo 'TAG=$TAG' >> .env &&
  docker compose pull &&
  docker compose run --rm migrate &&
  docker compose up -d --wait db redis backend nginx &&
  docker compose ps
"
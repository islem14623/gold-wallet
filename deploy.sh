#!/usr/bin/env bash
set -euo pipefail

SERVER=ubuntu@10.97.0.18
KEY=~/.ssh/gold-server

scp -i "$KEY" docker-compose.prod.yml "$SERVER":~/gold-wallet/docker-compose.yml
ssh -i "$KEY" "$SERVER" '
  cd ~/gold-wallet &&
  docker compose pull &&
  docker compose run --rm migrate &&
  docker compose up -d --wait db redis backend nginx &&
  docker compose ps
'
#!/usr/bin/env bash

MILVUS_COMPOSE="milvus-standalone.yml"
MILVUS_URI="https://github.com/milvus-io/milvus/releases/download/v2.6.0-rc1/milvus-standalone-docker-compose.yml"

if [[ -f "$MILVUS_COMPOSE" ]]; then
  if [[ -n "$(find "$MILVUS_COMPOSE" -mtime +30 2>/dev/null)" ]]; then
    docker compose -f "$MILVUS_COMPOSE" down --remove-orphans
    echo "Downloading Milvus docker compose file..."
    wget "$MILVUS_URI" -O "$MILVUS_COMPOSE"
  else
    echo "Milvus docker compose file is recent (less than 1 month old)"
    docker compose -f "$MILVUS_COMPOSE" down --remove-orphans
  fi
else
  ## Reverse order of operations in this case
  wget "$MILVUS_URI" -O "$MILVUS_COMPOSE"
  docker compose -f "$MILVUS_COMPOSE" down --remove-orphans
fi

if ! grep -q "MILVUSAI_OPENAI_API_KEY:" milvus-standalone.yml; then
  awk '{
    print $0;
    if ($0 ~ /standalone:/) { in_standalone = 1; }
    if (in_standalone && $0 ~ /environment:/) {
      print "      MILVUSAI_OPENAI_API_KEY: ${OPENAI_API_KEY}";
    }
  }' milvus-standalone.yml >milvus-standalone.yml.tmp && mv milvus-standalone.yml.tmp milvus-standalone.yml
  echo "Added MILVUSAI_OPENAI_API_KEY to milvus-standalone.yml"
else
  echo "MILVUSAI_OPENAI_API_KEY already exists in milvus-standalone.yml"
fi
docker compose -f "$MILVUS_COMPOSE" up -d

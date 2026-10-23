#!/bin/sh
# Writes a .env for a self-hosted Langfuse with fresh random secrets, plus a
# pre-created org, project, API key pair and admin login (LANGFUSE_INIT_*).
#
#   ./gen-env.sh <host-ip> <admin-email>
#
# The project's API keys and the admin password end up in the generated .env.
set -e
[ $# -eq 2 ] || { echo "usage: $0 <host-ip> <admin-email>"; exit 1; }
[ -f .env ] && { echo ".env already exists, refusing to overwrite"; exit 1; }
HOST=$1
EMAIL=$2
h() { openssl rand -hex "$1"; }
PG=$(h 16); MINIO=$(h 16)
umask 077
cat > .env <<ENV
NEXTAUTH_URL=http://$HOST:3000
NEXTAUTH_SECRET=$(h 32)
SALT=$(h 32)
ENCRYPTION_KEY=$(h 32)
TELEMETRY_ENABLED=false

POSTGRES_PASSWORD=$PG
DATABASE_URL=postgresql://postgres:$PG@postgres:5432/postgres
CLICKHOUSE_PASSWORD=$(h 16)
REDIS_AUTH=$(h 16)

MINIO_ROOT_PASSWORD=$MINIO
LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY=$MINIO
LANGFUSE_S3_MEDIA_UPLOAD_SECRET_ACCESS_KEY=$MINIO
LANGFUSE_S3_BATCH_EXPORT_SECRET_ACCESS_KEY=$MINIO
# Browser-facing MinIO address (media uploads/exports), so it must be the LAN IP
LANGFUSE_S3_MEDIA_UPLOAD_ENDPOINT=http://$HOST:9090
LANGFUSE_S3_BATCH_EXPORT_EXTERNAL_ENDPOINT=http://$HOST:9090

LANGFUSE_INIT_ORG_ID=personal
LANGFUSE_INIT_ORG_NAME=Personal
LANGFUSE_INIT_PROJECT_ID=research-tool
LANGFUSE_INIT_PROJECT_NAME=multi-agent-research-tool
LANGFUSE_INIT_PROJECT_PUBLIC_KEY=pk-lf-$(cat /proc/sys/kernel/random/uuid)
LANGFUSE_INIT_PROJECT_SECRET_KEY=sk-lf-$(cat /proc/sys/kernel/random/uuid)
LANGFUSE_INIT_USER_EMAIL=$EMAIL
LANGFUSE_INIT_USER_NAME=Admin
LANGFUSE_INIT_USER_PASSWORD=$(h 12)
LANGFUSE_DISABLE_SIGNUP_ONBOARDING=true
ENV
echo "wrote .env"

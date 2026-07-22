#!/usr/bin/env bash
#
# Scope MinIO's browser CORS policy to specific app origins.
#
# Why this exists:
#   Presigned direct-to-MinIO uploads (FIMEVAL-BE16) make the browser PUT file
#   bytes straight to MinIO — a cross-origin request that needs CORS. MinIO does
#   NOT implement the S3 per-bucket PutBucketCors API (it returns NotImplemented);
#   CORS is a *server-level* setting applied with `mc admin config`.
#
# Do you need to run this?
#   - Local dev: usually NO. MinIO's `cors_allow_origin` defaults to `*`, so the
#     browser PUT already works out of the box.
#   - Production (or any hardened setup): YES. Replace the permissive `*` with the
#     exact origins your app is served from.
#
# NOTE (dev credentials): the defaults below are the local dev MinIO creds.
# Override every value via env vars for any non-dev deployment, and scrub these
# defaults before shipping production docs.
#
# Usage:
#   ./setup_minio_cors.sh
#   CORS_ALLOW_ORIGIN="https://fimeval.example.org" \
#     MINIO_ENDPOINT="https://minio.example.org" \
#     MINIO_ROOT_USER=... MINIO_ROOT_PASSWORD=... ./setup_minio_cors.sh
#
set -euo pipefail

ALIAS="${MINIO_ALIAS:-fimlocal}"
ENDPOINT="${MINIO_ENDPOINT:-http://127.0.0.1:9000}"
ACCESS_KEY="${MINIO_ROOT_USER:-admin}"
SECRET_KEY="${MINIO_ROOT_PASSWORD:-admin123}"

# Comma-separated browser origins allowed to upload directly to MinIO.
# Dev default covers the Tethys server and the Vite dev server on both hostnames.
ORIGINS="${CORS_ALLOW_ORIGIN:-http://127.0.0.1:8000,http://localhost:8000,http://127.0.0.1:5173,http://localhost:5173}"

command -v mc >/dev/null 2>&1 || {
  echo "error: MinIO client 'mc' not found on PATH" >&2
  exit 1
}

mc alias set "$ALIAS" "$ENDPOINT" "$ACCESS_KEY" "$SECRET_KEY" >/dev/null
mc admin config set "$ALIAS" api cors_allow_origin="$ORIGINS"
# The setting takes effect only after a service restart.
mc admin service restart "$ALIAS"

echo "MinIO CORS scoped to: $ORIGINS"
echo "Verify a preflight with:"
echo "  curl -s -D - -o /dev/null -X OPTIONS \\"
echo "    -H 'Origin: ${ORIGINS%%,*}' -H 'Access-Control-Request-Method: PUT' \\"
echo "    ${ENDPOINT}/ | grep -i access-control"

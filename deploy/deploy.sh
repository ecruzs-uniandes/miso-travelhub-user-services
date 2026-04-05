#!/usr/bin/env bash
set -euo pipefail

# --------------------------------------------------
# Deploy user-services a GCP Cloud Run
# Uso:
#   ./deploy/deploy.sh              # build + deploy
#   ./deploy/deploy.sh --only-db    # solo migrar BD
# --------------------------------------------------

PROJECT_ID="${GCP_PROJECT_ID:-gen-lang-client-0930444414}"
REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="user-services"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"
TAG="${DEPLOY_TAG:-latest}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()   { echo -e "${GREEN}[deploy]${NC} $1"; }
warn()  { echo -e "${YELLOW}[deploy]${NC} $1"; }
error() { echo -e "${RED}[deploy]${NC} $1" >&2; exit 1; }

# --------------------------------------------------
# Validaciones
# --------------------------------------------------
command -v gcloud >/dev/null 2>&1 || error "gcloud CLI no encontrado. Instalar: https://cloud.google.com/sdk/docs/install"
command -v docker >/dev/null 2>&1 || error "docker no encontrado."

CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null)
if [ "$CURRENT_PROJECT" != "$PROJECT_ID" ]; then
    warn "Proyecto actual: $CURRENT_PROJECT. Cambiando a $PROJECT_ID..."
    gcloud config set project "$PROJECT_ID"
fi

# --------------------------------------------------
# Migraciones (si se pasa --only-db, solo hace esto)
# --------------------------------------------------
run_migrations() {
    log "Ejecutando migraciones con Alembic..."
    if [ -z "${DATABASE_URL_SYNC:-}" ]; then
        warn "DATABASE_URL_SYNC no definida. Saltando migraciones."
        warn "Ejecutar manualmente: DATABASE_URL_SYNC=<url> alembic upgrade head"
        return
    fi
    alembic upgrade head
    log "Migraciones aplicadas."
}

if [ "${1:-}" = "--only-db" ]; then
    run_migrations
    exit 0
fi

# --------------------------------------------------
# Build
# --------------------------------------------------
log "Construyendo imagen: ${IMAGE}:${TAG}"
docker build \
    --target production \
    -t "${IMAGE}:${TAG}" \
    .

# --------------------------------------------------
# Push a Container Registry
# --------------------------------------------------
log "Autenticando Docker con GCR..."
gcloud auth configure-docker gcr.io --quiet

log "Subiendo imagen a gcr.io..."
docker push "${IMAGE}:${TAG}"

# --------------------------------------------------
# Deploy a Cloud Run
# --------------------------------------------------
log "Desplegando ${SERVICE_NAME} en Cloud Run (${REGION})..."
gcloud run deploy "$SERVICE_NAME" \
    --image "${IMAGE}:${TAG}" \
    --region "$REGION" \
    --platform managed \
    --port 8000 \
    --allow-unauthenticated \
    --vpc-connector travelhub-connector \
    --memory 512Mi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 10 \
    --set-env-vars "\
JWT_ISSUER=https://auth.travelhub.app,\
JWT_AUDIENCE=travelhub-api,\
JWT_ALGORITHM=RS256,\
JWT_ACCESS_TTL=900,\
JWT_REFRESH_TTL=604800,\
ENVIRONMENT=production,\
DEBUG=false" \
    --quiet

# --------------------------------------------------
# Obtener URL del servicio
# --------------------------------------------------
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
    --region "$REGION" \
    --format "value(status.url)")

log "Deploy exitoso!"
echo ""
echo "=========================================="
echo "  URL: ${SERVICE_URL}"
echo "  Health: ${SERVICE_URL}/health"
echo "  JWKS: ${SERVICE_URL}/.well-known/jwks.json"
echo "=========================================="
echo ""
warn "SIGUIENTE PASO: Reportar la URL al equipo de infra para actualizar el API Gateway."
warn "  1. Reemplazar PLACEHOLDER en gateway/openapi-spec.yaml con: ${SERVICE_URL}"
warn "  2. Ejecutar: bash deploy/deploy-gateway.sh"

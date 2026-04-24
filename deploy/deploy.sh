#!/usr/bin/env bash
set -euo pipefail

# --------------------------------------------------
# Deploy user-services a GCP Cloud Run (dev o prod)
# Uso:
#   ./deploy/deploy.sh dev                  # build + deploy a DEV
#   ./deploy/deploy.sh prod                 # build + deploy a PROD
#   ./deploy/deploy.sh dev --only-migrate   # solo correr migraciones en DEV
#   ./deploy/deploy.sh prod --only-migrate  # solo correr migraciones en PROD
# --------------------------------------------------

ENVIRONMENT="${1:-}"
MODE="${2:-full}"

if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]]; then
    echo "ERROR: primer argumento debe ser 'dev' o 'prod'" >&2
    echo "Uso: $0 {dev|prod} [--only-migrate]" >&2
    exit 1
fi

# Config por ambiente
if [ "$ENVIRONMENT" = "dev" ]; then
    PROJECT_ID="gen-lang-client-0930444414"
    VPC_CONNECTOR="travelhub-connector"
    ENV_NAME="development"
    DEBUG="true"
else
    PROJECT_ID="travelhub-prod-492116"
    VPC_CONNECTOR="prod-travelhub-connector"
    ENV_NAME="production"
    DEBUG="false"
fi

REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="user-services"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${SERVICE_NAME}/${SERVICE_NAME}"
TAG="${DEPLOY_TAG:-latest}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()   { echo -e "${GREEN}[deploy-${ENVIRONMENT}]${NC} $1"; }
warn()  { echo -e "${YELLOW}[deploy-${ENVIRONMENT}]${NC} $1"; }
error() { echo -e "${RED}[deploy-${ENVIRONMENT}]${NC} $1" >&2; exit 1; }

# --------------------------------------------------
# Validaciones
# --------------------------------------------------
command -v gcloud >/dev/null 2>&1 || error "gcloud CLI no encontrado."
command -v docker >/dev/null 2>&1 || error "docker no encontrado."

CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null || echo "")
if [ "$CURRENT_PROJECT" != "$PROJECT_ID" ]; then
    warn "Proyecto actual: $CURRENT_PROJECT. Cambiando a $PROJECT_ID..."
    gcloud config set project "$PROJECT_ID"
fi

# --------------------------------------------------
# Migraciones via Cloud Build (usa secret DATABASE_URL_SYNC)
# --------------------------------------------------
run_migrations() {
    log "Ejecutando migraciones via Cloud Build (secret DATABASE_URL_SYNC de ${PROJECT_ID})..."
    gcloud builds submit \
        --project="$PROJECT_ID" \
        --config=deploy/migrate.yaml \
        --substitutions=_TAG="${TAG}" \
        --no-source
    log "Migraciones aplicadas."
}

if [ "$MODE" = "--only-migrate" ]; then
    run_migrations
    exit 0
fi

# --------------------------------------------------
# Build
# --------------------------------------------------
log "Autenticando Docker con Artifact Registry ${REGION}..."
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

log "Construyendo imagen: ${IMAGE}:${TAG}"
docker build --target production -t "${IMAGE}:${TAG}" .

log "Subiendo imagen a Artifact Registry..."
docker push "${IMAGE}:${TAG}"

# --------------------------------------------------
# Migraciones (antes del deploy)
# --------------------------------------------------
run_migrations

# --------------------------------------------------
# Deploy a Cloud Run
# --------------------------------------------------
log "Desplegando ${SERVICE_NAME} en Cloud Run (${REGION}) proyecto ${PROJECT_ID}..."
gcloud run deploy "$SERVICE_NAME" \
    --project="$PROJECT_ID" \
    --image="${IMAGE}:${TAG}" \
    --region="$REGION" \
    --platform=managed \
    --port=8000 \
    --allow-unauthenticated \
    --vpc-connector="$VPC_CONNECTOR" \
    --memory=512Mi \
    --cpu=1 \
    --min-instances=0 \
    --max-instances=10 \
    --set-env-vars="ENVIRONMENT=${ENV_NAME},DEBUG=${DEBUG},JWT_ALGORITHM=RS256,JWT_ISSUER=https://auth.travelhub.app,JWT_AUDIENCE=travelhub-api,JWT_ACCESS_TTL=900,JWT_REFRESH_TTL=604800,RATE_LIMIT_REQUESTS=100,RATE_LIMIT_WINDOW_SECONDS=60" \
    --set-secrets="DATABASE_URL=DATABASE_URL:latest,DATABASE_URL_SYNC=DATABASE_URL_SYNC:latest,RSA_PRIVATE_KEY_B64=RSA_PRIVATE_KEY_B64:latest" \
    --quiet

SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --format="value(status.url)")

log "Deploy exitoso!"
echo ""
echo "=========================================="
echo "  Ambiente: ${ENVIRONMENT} (${PROJECT_ID})"
echo "  URL: ${SERVICE_URL}"
echo "  Health: ${SERVICE_URL}/health"
echo "  JWKS: ${SERVICE_URL}/.well-known/jwks.json"
echo "=========================================="

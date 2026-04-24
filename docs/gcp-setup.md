# Guia de Configuracion GCP para CI/CD

Esta guia describe la configuracion actual de infraestructura en GCP y GitHub Actions para el servicio `user-services`. Autenticacion vía **Workload Identity Federation (WIF)**, sin service account keys.

---

## Tabla de Contenidos

1. [Arquitectura CI/CD](#arquitectura-cicd)
2. [Proyectos y recursos GCP](#proyectos-y-recursos-gcp)
3. [Configuracion DEV (one-time)](#configuracion-dev)
4. [Configuracion PROD (one-time)](#configuracion-prod)
5. [Workload Identity Federation (WIF)](#workload-identity-federation-wif)
6. [Cloud Deploy canary](#cloud-deploy-canary)
7. [GitHub Actions](#github-actions)
8. [Verificacion](#verificacion)
9. [Despliegue manual (script)](#despliegue-manual)
10. [Troubleshooting](#troubleshooting)

---

## Arquitectura CI/CD

```
                 GitHub Push
                     |
                     v
          +---------------------+
          | GitHub Actions      |
          | (ci.yml)            |
          |                     |
          | OIDC Token Request  |
          +----------+----------+
                     |
                     v
          +---------------------+
          | Workload Identity   |
          | Federation (GCP)    |
          | - Valida issuer     |
          | - Valida claims     |
          | - Restringe por ref |
          +----------+----------+
                     |
                     v
          +---------------------+
          | Service Account     |
          | github-deploy       |
          +----------+----------+
                     |
          +----------+----------+
          |                     |
          v                     v
    +----------+        +---------------+
    |  DEV     |        |  PROD         |
    | Cloud    |        | Cloud Deploy  |
    | Run      |        | (canary 10%-> |
    | (direct) |        |  50% -> 100%) |
    +----------+        +---------------+
```

**DEV:** push a `develop` o `feature/*` -> deploy directo a Cloud Run.
**PROD:** push a `main` -> release en Cloud Deploy con canary progresivo y aprobaciones.

---

## Proyectos y recursos GCP

### DEV — `gen-lang-client-0930444414`

| Recurso | Nombre / valor |
|---|---|
| Project number | `154299161799` |
| Region | `us-central1` |
| Service Account | `github-deploy@gen-lang-client-0930444414.iam.gserviceaccount.com` |
| WIF Pool | `github-pool` |
| WIF Provider | `github-provider` |
| Artifact Registry | `us-central1-docker.pkg.dev/gen-lang-client-0930444414/user-services` |
| Cloud SQL | `travelhub-db` (IP privada `10.100.0.3`) |
| VPC Connector | `travelhub-connector` |
| Secrets | `DATABASE_URL`, `DATABASE_URL_SYNC`, `RSA_PRIVATE_KEY_B64` |
| Cloud Run service | `user-services` |

### PROD — `travelhub-prod-492116`

| Recurso | Nombre / valor |
|---|---|
| Project number | `974898737307` |
| Region | `us-central1` |
| Service Account | `github-deploy@travelhub-prod-492116.iam.gserviceaccount.com` |
| WIF Pool | `github-pool` |
| WIF Provider | `github-provider` |
| Artifact Registry | `us-central1-docker.pkg.dev/travelhub-prod-492116/user-services` |
| Cloud SQL | `prod-travelhub-db` (IP privada `10.200.0.3`) |
| VPC Connector | `prod-travelhub-connector` |
| Secrets | `DATABASE_URL`, `DATABASE_URL_SYNC`, `RSA_PRIVATE_KEY_B64`, `prod-travelhub-db-password` |
| Cloud Deploy pipeline | `user-services` |
| Cloud Run service | `user-services` |

---

## Configuracion DEV

> **Solo necesitas ejecutar estos pasos una vez.** La infraestructura actual ya esta configurada; esta seccion es para replicar o entender la configuracion.

### 1. Habilitar APIs

```bash
gcloud services enable \
  artifactregistry.googleapis.com \
  run.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com \
  iamcredentials.googleapis.com \
  --project=gen-lang-client-0930444414
```

### 2. Artifact Registry, Service Account y WIF

Ver seccion [Workload Identity Federation (WIF)](#workload-identity-federation-wif) con el detalle completo.

### 3. Generar clave RSA e ingresar a Secret Manager

```bash
# Generar clave RSA 2048 en PKCS#8 (formato requerido por python-jose)
openssl genrsa -out private_traditional.pem 2048
openssl pkcs8 -topk8 -nocrypt -in private_traditional.pem -out private.pem

# Subir a Secret Manager como base64
base64 -i private.pem | tr -d '\n' | \
  gcloud secrets create RSA_PRIVATE_KEY_B64 \
    --project=gen-lang-client-0930444414 \
    --replication-policy=automatic --data-file=-

# Limpiar archivos temporales
rm private_traditional.pem private.pem
```

### 4. Crear secrets DATABASE_URL

```bash
DEV_DB_USER="travelhub_app"
DEV_DB_PASS="<password_de_travelhub_app_en_dev>"
DEV_DB_IP="10.100.0.3"
DEV_DB_NAME="travelhub"  # o travelhub_users, segun instancia

echo -n "postgresql+asyncpg://${DEV_DB_USER}:${DEV_DB_PASS}@${DEV_DB_IP}:5432/${DEV_DB_NAME}" | \
  gcloud secrets create DATABASE_URL \
    --project=gen-lang-client-0930444414 --replication-policy=automatic --data-file=-

echo -n "postgresql+psycopg2://${DEV_DB_USER}:${DEV_DB_PASS}@${DEV_DB_IP}:5432/${DEV_DB_NAME}" | \
  gcloud secrets create DATABASE_URL_SYNC \
    --project=gen-lang-client-0930444414 --replication-policy=automatic --data-file=-
```

---

## Configuracion PROD

### 1. Habilitar APIs

```bash
gcloud services enable \
  artifactregistry.googleapis.com \
  run.googleapis.com \
  clouddeploy.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com \
  iamcredentials.googleapis.com \
  vpcaccess.googleapis.com \
  sqladmin.googleapis.com \
  iam.googleapis.com \
  --project=travelhub-prod-492116
```

### 2. Crear Artifact Registry repo

```bash
gcloud artifacts repositories create user-services \
  --project=travelhub-prod-492116 \
  --location=us-central1 \
  --repository-format=docker \
  --description="user-services prod images"
```

### 3. Service Account para GitHub Actions

```bash
gcloud iam service-accounts create github-deploy \
  --project=travelhub-prod-492116 \
  --display-name="GitHub Actions Deploy (user-services prod)"

SA="github-deploy@travelhub-prod-492116.iam.gserviceaccount.com"
PROJECT=travelhub-prod-492116

for ROLE in \
    roles/run.admin \
    roles/artifactregistry.writer \
    roles/storage.admin \
    roles/logging.logWriter \
    roles/cloudbuild.builds.editor \
    roles/clouddeploy.releaser \
    roles/clouddeploy.operator \
    roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding $PROJECT \
    --member="serviceAccount:${SA}" \
    --role="$ROLE" --condition=None --quiet
done
```

### 4. Dar permiso al SA sobre los 3 secrets

```bash
SA="github-deploy@travelhub-prod-492116.iam.gserviceaccount.com"
for SECRET in DATABASE_URL DATABASE_URL_SYNC RSA_PRIVATE_KEY_B64; do
  gcloud secrets add-iam-policy-binding "$SECRET" \
    --project=travelhub-prod-492116 \
    --member="serviceAccount:${SA}" \
    --role="roles/secretmanager.secretAccessor" --quiet
done
```

### 5. Permisos al runtime de Cloud Run (Compute default SA)

```bash
COMPUTE_SA="974898737307-compute@developer.gserviceaccount.com"

# Para que pueda leer secrets en runtime
for SECRET in DATABASE_URL DATABASE_URL_SYNC RSA_PRIVATE_KEY_B64; do
  gcloud secrets add-iam-policy-binding "$SECRET" \
    --project=travelhub-prod-492116 \
    --member="serviceAccount:${COMPUTE_SA}" \
    --role="roles/secretmanager.secretAccessor" --quiet
done

# Para que Cloud Deploy pueda orquestar deployments
for ROLE in \
    roles/clouddeploy.jobRunner \
    roles/run.admin \
    roles/iam.serviceAccountUser \
    roles/artifactregistry.reader \
    roles/storage.admin \
    roles/logging.logWriter \
    roles/artifactregistry.writer \
    roles/cloudbuild.builds.builder; do
  gcloud projects add-iam-policy-binding travelhub-prod-492116 \
    --member="serviceAccount:${COMPUTE_SA}" \
    --role="$ROLE" --condition=None --quiet
done
```

### 6. Generar clave RSA y secrets

```bash
# RSA 2048 PKCS#8
openssl genrsa -out priv_trad.pem 2048
openssl pkcs8 -topk8 -nocrypt -in priv_trad.pem -out priv.pem
base64 -i priv.pem | tr -d '\n' | \
  gcloud secrets create RSA_PRIVATE_KEY_B64 \
    --project=travelhub-prod-492116 --replication-policy=automatic --data-file=-
rm priv_trad.pem priv.pem

# DATABASE_URL usando prod-travelhub-db-password ya existente
PROD_DB_PASS=$(gcloud secrets versions access latest \
  --secret=prod-travelhub-db-password --project=travelhub-prod-492116)

# Sincronizar user de Cloud SQL con ese password
gcloud sql users set-password travelhub_app \
  --instance=prod-travelhub-db --project=travelhub-prod-492116 \
  --password="$PROD_DB_PASS"

echo -n "postgresql+asyncpg://travelhub_app:${PROD_DB_PASS}@10.200.0.3:5432/travelhub" | \
  gcloud secrets create DATABASE_URL \
    --project=travelhub-prod-492116 --replication-policy=automatic --data-file=-

echo -n "postgresql+psycopg2://travelhub_app:${PROD_DB_PASS}@10.200.0.3:5432/travelhub" | \
  gcloud secrets create DATABASE_URL_SYNC \
    --project=travelhub-prod-492116 --replication-policy=automatic --data-file=-
```

### 7. Aplicar pipeline de Cloud Deploy

```bash
gcloud deploy apply \
  --file=clouddeploy.yaml \
  --region=us-central1 \
  --project=travelhub-prod-492116
```

---

## Workload Identity Federation (WIF)

WIF reemplaza los service account keys. GitHub Actions obtiene un token OIDC de GitHub, GCP lo valida y emite un token de acceso temporal.

### Crear WIF Pool y Provider (por ambiente)

**DEV** (permite `develop` y `feature/*`):

```bash
REPO="ecruzs-uniandes/miso-travelhub-user-services"
PROJECT=gen-lang-client-0930444414
PROJECT_NUMBER=154299161799

gcloud iam workload-identity-pools create github-pool \
  --project=$PROJECT --location=global \
  --display-name="GitHub Actions Pool"

gcloud iam workload-identity-pools providers create-oidc github-provider \
  --project=$PROJECT --location=global \
  --workload-identity-pool=github-pool \
  --display-name="GitHub OIDC (develop + feature)" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner,attribute.ref=assertion.ref,attribute.actor=assertion.actor" \
  --attribute-condition="assertion.repository=='${REPO}' && (assertion.ref=='refs/heads/develop' || assertion.ref.startsWith('refs/heads/feature/'))" \
  --issuer-uri="https://token.actions.githubusercontent.com"

gcloud iam service-accounts add-iam-policy-binding \
  "github-deploy@${PROJECT}.iam.gserviceaccount.com" \
  --project=$PROJECT \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/attribute.repository/${REPO}"
```

**PROD** (solo `main`):

```bash
REPO="ecruzs-uniandes/miso-travelhub-user-services"
PROJECT=travelhub-prod-492116
PROJECT_NUMBER=974898737307

gcloud iam workload-identity-pools create github-pool \
  --project=$PROJECT --location=global \
  --display-name="GitHub Actions Pool"

gcloud iam workload-identity-pools providers create-oidc github-provider \
  --project=$PROJECT --location=global \
  --workload-identity-pool=github-pool \
  --display-name="GitHub OIDC (main only)" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner,attribute.ref=assertion.ref,attribute.actor=assertion.actor" \
  --attribute-condition="assertion.repository=='${REPO}' && assertion.ref=='refs/heads/main'" \
  --issuer-uri="https://token.actions.githubusercontent.com"

gcloud iam service-accounts add-iam-policy-binding \
  "github-deploy@${PROJECT}.iam.gserviceaccount.com" \
  --project=$PROJECT \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/attribute.repository/${REPO}"
```

### Referencias usadas en `ci.yml`

Los valores estan **hardcoded en `ci.yml`** (no son secretos — son identificadores publicos):

```yaml
env:
  DEV_WIF_PROVIDER: projects/154299161799/locations/global/workloadIdentityPools/github-pool/providers/github-provider
  DEV_SA: github-deploy@gen-lang-client-0930444414.iam.gserviceaccount.com
  PROD_WIF_PROVIDER: projects/974898737307/locations/global/workloadIdentityPools/github-pool/providers/github-provider
  PROD_SA: github-deploy@travelhub-prod-492116.iam.gserviceaccount.com
```

Y cada job de deploy necesita:

```yaml
permissions:
  contents: read
  id-token: write   # indispensable para que GitHub emita el OIDC token

steps:
  - uses: google-github-actions/auth@v2
    with:
      workload_identity_provider: ${{ env.PROD_WIF_PROVIDER }}
      service_account: ${{ env.PROD_SA }}
```

---

## Cloud Deploy canary

`clouddeploy.yaml` define:

```yaml
serialPipeline:
  stages:
    - targetId: prod
      strategy:
        canary:
          runtimeConfig:
            cloudRun:
              automaticTrafficControl: true
          canaryDeployment:
            percentages: [10, 50]
            verify: true
---
kind: Target
metadata:
  name: prod
requireApproval: true
run:
  location: projects/travelhub-prod-492116/locations/us-central1
```

Flujo completo de cada release en prod:

1. `gcloud deploy releases create` crea el release → estado `PENDING_APPROVAL`
2. Aprobar via consola → fase `canary-10` deploya al 10% + corre `verify` (health check)
3. Aprobar fase siguiente → `canary-50` (50% + verify)
4. Aprobar fase final → `stable` (100%)

> **Nota sobre primer deploy**: cuando no hay una revision previa gestionada por Cloud Deploy, las fases canary se saltan automaticamente y va directo a `stable` al 100%. Los siguientes releases si haran canary progresivo real.

### Verify step (skaffold.yaml)

```yaml
verify:
  - name: verify-health
    container:
      image: gcr.io/google.com/cloudsdktool/cloud-sdk:slim
      command: ["/bin/sh"]
      args:
        - "-c"
        - |
          SERVICE_URL=$(echo $CLOUD_RUN_SERVICE_URLS | cut -d',' -f1)
          for i in 1 2 3 4 5; do
            STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${SERVICE_URL}/health" || true)
            [ "$STATUS" = "200" ] && exit 0
            sleep 10
          done
          exit 1
```

Requiere ingress `all` en el Cloud Run para que el health check se pueda hacer desde el contenedor de verify (que vive fuera del VPC).

---

## Migraciones Alembic en PROD

Cloud Build **no tiene acceso al VPC privado** de Cloud SQL. Las migraciones se corren como **Cloud Run Job** con VPC connector:

```bash
gcloud run jobs deploy user-services-migrate \
  --project=travelhub-prod-492116 --region=us-central1 \
  --image=us-central1-docker.pkg.dev/travelhub-prod-492116/user-services/user-services:TAG \
  --vpc-connector=prod-travelhub-connector \
  --set-secrets=DATABASE_URL_SYNC=DATABASE_URL_SYNC:latest \
  --command=sh --args="-c,cd /app && alembic upgrade head" \
  --max-retries=1 --task-timeout=300

gcloud run jobs execute user-services-migrate \
  --project=travelhub-prod-492116 --region=us-central1 --wait
```

Este flujo esta automatizado en el job `deploy-prod` del `ci.yml` antes del `gcloud deploy releases create`.

---

## GitHub Actions

### `ci.yml` — flujo

| Rama | Jobs ejecutados |
|---|---|
| `feature/*`, `develop` | tests + lint + **deploy-dev** (Cloud Run directo) |
| `main` | tests + lint + migraciones prod + **deploy-prod** (Cloud Deploy canary) |
| PR → `main`/`develop` | tests + lint + **docker-build** (solo validacion) |

### Secretos en GitHub

**Con WIF, no se requiere `GCP_SA_KEY` ni `GCP_PROJECT_ID`.** Todos los identificadores estan hardcoded en `ci.yml` (no son sensibles).

> Si en el futuro necesitas rotar credenciales, solo borras el binding del WIF pool. No hay keys que gestionar.

---

## Verificacion

```bash
# Cloud Run service en prod
gcloud run services describe user-services \
  --project=travelhub-prod-492116 --region=us-central1 \
  --format="value(status.url,status.latestReadyRevisionName)"

# Pipeline de Cloud Deploy
gcloud deploy delivery-pipelines describe user-services \
  --project=travelhub-prod-492116 --region=us-central1

# WIF Provider
gcloud iam workload-identity-pools providers describe github-provider \
  --project=travelhub-prod-492116 --location=global \
  --workload-identity-pool=github-pool \
  --format="value(state,attributeCondition)"

# Secrets
gcloud secrets list --project=travelhub-prod-492116

# Health check
curl https://user-services-qhweqfkejq-uc.a.run.app/health
```

---

## Despliegue manual

El script `deploy/deploy.sh` soporta ambos ambientes:

```bash
# Dev
./deploy/deploy.sh dev                  # build + migraciones + deploy
./deploy/deploy.sh dev --only-migrate   # solo migraciones

# Prod
./deploy/deploy.sh prod                 # build + migraciones + deploy
./deploy/deploy.sh prod --only-migrate  # solo migraciones
```

El script:
1. Detecta el proyecto segun el argumento (`dev`/`prod`)
2. Cambia la config activa de gcloud
3. Construye y pushea la imagen a Artifact Registry
4. Ejecuta migraciones via Cloud Build (con secret DATABASE_URL_SYNC)
5. Despliega a Cloud Run con todos los secrets inyectados

> **Nota:** el script NO usa Cloud Deploy (es deploy directo). Para canary en prod, usar GitHub Actions push a `main`, o crear manualmente un release con `gcloud deploy releases create`.

### Deploy manual via Cloud Deploy

```bash
RELEASE_NAME="manual-$(date +%Y%m%d-%H%M%S)"
gcloud deploy releases create "$RELEASE_NAME" \
  --project=travelhub-prod-492116 --region=us-central1 \
  --delivery-pipeline=user-services \
  --images=user-services=us-central1-docker.pkg.dev/travelhub-prod-492116/user-services/user-services:latest \
  --skaffold-file=skaffold.yaml
```

Luego aprobar cada fase en la [consola de Cloud Deploy](https://console.cloud.google.com/deploy/delivery-pipelines/us-central1/user-services?project=travelhub-prod-492116).

---

## Troubleshooting

### Error: "Permission 'secretmanager.versions.access' denied"

Faltan permisos al SA. Ejecutar binding correspondiente:
```bash
gcloud secrets add-iam-policy-binding DATABASE_URL \
  --project=<PROJECT_ID> \
  --member="serviceAccount:github-deploy@<PROJECT_ID>.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

### Error: "Connection timed out" al correr migraciones

Cloud Build no puede alcanzar la IP privada de Cloud SQL. Usar Cloud Run Job con VPC connector (ver seccion [Migraciones Alembic en PROD](#migraciones-alembic-en-prod)).

### Error: "No config file 'alembic.ini' found"

Cloud Build o Cloud Run Job corren con WORKDIR `/workspace`. Usar entrypoint `sh -c "cd /app && alembic upgrade head"`.

### Error: WIF "The attribute condition must reference one of the provider's claims"

Verificar que el `attribute-mapping` incluye los claims referenciados en `attribute-condition`. Ambos usan el prefijo `assertion.` (viene del JWT de GitHub).

### Error: "Could not determine join condition" al arrancar la app

Modelos SQLAlchemy desalineados con el schema real de DB. Verificar que el modelo del servicio refleja las columnas reales de la tabla.

### Error: "Container failed startup probe" en Cloud Run

Causas comunes:
- VPC connector no asignado (no puede conectar a Cloud SQL privada)
- `DATABASE_URL` mal formada (revisar en Secret Manager)
- El secreto `RSA_PRIVATE_KEY_B64` no existe o no esta en formato PKCS#8 + base64

Revisar logs:
```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=user-services" \
  --project=travelhub-prod-492116 --limit=30 --format="value(textPayload)"
```

### El primer release en Cloud Deploy salta las fases canary

Comportamiento **esperado**. Cloud Deploy necesita una revision previa gestionada para hacer split de trafico. El primer deploy va directo a `stable` al 100%. Todos los siguientes haran canary real (10% → 50% → 100%).

### Rollback

Desde la consola de Cloud Deploy: **Rollback** en el release previo. Automaticamente crea un nuevo release apuntando a la imagen anterior.

# Guia de Configuracion GCP para CI/CD

Esta guia describe los pasos necesarios para configurar la infraestructura en Google Cloud Platform y GitHub Actions antes del primer despliegue. Solo es necesario ejecutar estos pasos **una vez por proyecto/ambiente**.

---

## Tabla de Contenidos

1. [Prerequisitos](#prerequisitos)
2. [Configuracion del ambiente DEV](#configuracion-del-ambiente-dev)
3. [Configuracion del ambiente PROD](#configuracion-del-ambiente-prod)
4. [Configuracion de GitHub Secrets](#configuracion-de-github-secrets)
5. [Verificacion](#verificacion)
6. [Flujo CI/CD](#flujo-cicd)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisitos

- [Google Cloud SDK (gcloud)](https://cloud.google.com/sdk/docs/install) instalado y autenticado
- [GitHub CLI (gh)](https://cli.github.com/) instalado y autenticado
- Acceso de admin al repositorio en GitHub
- Acceso de Owner o Editor al proyecto de GCP

```bash
# Verificar autenticacion
gcloud auth list
gh auth status
```

---

## Configuracion del ambiente DEV

**Proyecto GCP:** `gen-lang-client-0930444414`
**Region:** `us-central1`

### 1. Habilitar APIs

```bash
gcloud services enable \
  artifactregistry.googleapis.com \
  run.googleapis.com \
  secretmanager.googleapis.com \
  --project=gen-lang-client-0930444414
```

### 2. Crear repositorio en Artifact Registry

```bash
gcloud artifacts repositories create user-services \
  --repository-format=docker \
  --location=us-central1 \
  --project=gen-lang-client-0930444414
```

### 3. Crear Service Account para GitHub Actions

```bash
gcloud iam service-accounts create github-deploy \
  --display-name="GitHub Actions Deploy" \
  --project=gen-lang-client-0930444414
```

### 4. Asignar roles a la Service Account

```bash
SA_EMAIL="github-deploy@gen-lang-client-0930444414.iam.gserviceaccount.com"

for role in run.admin artifactregistry.writer iam.serviceAccountUser storage.admin; do
  gcloud projects add-iam-policy-binding gen-lang-client-0930444414 \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/${role}" \
    --condition=None --quiet
done
```

### 5. Crear secrets en Secret Manager

```bash
# DATABASE_URL (async - para la aplicacion)
printf "postgresql+asyncpg://USER:PASSWORD@HOST:5432/travelhub_users" | \
  gcloud secrets create DATABASE_URL \
    --data-file=- \
    --project=gen-lang-client-0930444414

# DATABASE_URL_SYNC (sync - para Alembic)
printf "postgresql+psycopg2://USER:PASSWORD@HOST:5432/travelhub_users" | \
  gcloud secrets create DATABASE_URL_SYNC \
    --data-file=- \
    --project=gen-lang-client-0930444414
```

> Reemplazar `USER`, `PASSWORD` y `HOST` con los valores reales de la base de datos.

### 6. Dar acceso a los secrets

```bash
SA_EMAIL="github-deploy@gen-lang-client-0930444414.iam.gserviceaccount.com"
# Obtener el numero del proyecto para la SA de Cloud Run
PROJECT_NUMBER=$(gcloud projects describe gen-lang-client-0930444414 --format="value(projectNumber)")
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

for secret in DATABASE_URL DATABASE_URL_SYNC; do
  # SA de GitHub Actions (para el deploy)
  gcloud secrets add-iam-policy-binding ${secret} \
    --project=gen-lang-client-0930444414 \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/secretmanager.secretAccessor" --quiet

  # SA de Cloud Run (para leer en runtime)
  gcloud secrets add-iam-policy-binding ${secret} \
    --project=gen-lang-client-0930444414 \
    --member="serviceAccount:${COMPUTE_SA}" \
    --role="roles/secretmanager.secretAccessor" --quiet
done
```

### 7. Generar clave JSON de la Service Account

```bash
gcloud iam service-accounts keys create key-dev.json \
  --iam-account=github-deploy@gen-lang-client-0930444414.iam.gserviceaccount.com
```

> **IMPORTANTE:** Este archivo contiene credenciales sensibles. No subirlo al repositorio. Eliminarlo despues de configurar el secret en GitHub.

---

## Configuracion del ambiente PROD

**Proyecto GCP:** `<PROD_PROJECT_ID>` (reemplazar en todos los comandos)
**Region:** `us-central1`

### 1. Habilitar APIs

```bash
gcloud services enable \
  artifactregistry.googleapis.com \
  run.googleapis.com \
  clouddeploy.googleapis.com \
  secretmanager.googleapis.com \
  --project=<PROD_PROJECT_ID>
```

> Nota: produccion requiere `clouddeploy.googleapis.com` adicional (para el despliegue canary).

### 2. Crear repositorio en Artifact Registry

```bash
gcloud artifacts repositories create user-services \
  --repository-format=docker \
  --location=us-central1 \
  --project=<PROD_PROJECT_ID>
```

### 3. Crear Service Account para GitHub Actions

```bash
gcloud iam service-accounts create github-deploy \
  --display-name="GitHub Actions Deploy" \
  --project=<PROD_PROJECT_ID>
```

### 4. Asignar roles a la Service Account

```bash
SA_EMAIL="github-deploy@<PROD_PROJECT_ID>.iam.gserviceaccount.com"

for role in clouddeploy.releaser run.admin artifactregistry.writer \
  iam.serviceAccountUser storage.admin secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding <PROD_PROJECT_ID> \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/${role}" \
    --condition=None --quiet
done
```

> Nota: produccion requiere `clouddeploy.releaser` adicional.

### 5. Crear secrets en Secret Manager

```bash
printf "postgresql+asyncpg://USER:PASSWORD@HOST:5432/travelhub_users" | \
  gcloud secrets create DATABASE_URL \
    --data-file=- \
    --project=<PROD_PROJECT_ID>

printf "postgresql+psycopg2://USER:PASSWORD@HOST:5432/travelhub_users" | \
  gcloud secrets create DATABASE_URL_SYNC \
    --data-file=- \
    --project=<PROD_PROJECT_ID>
```

### 6. Dar acceso a los secrets

```bash
SA_EMAIL="github-deploy@<PROD_PROJECT_ID>.iam.gserviceaccount.com"
PROJECT_NUMBER=$(gcloud projects describe <PROD_PROJECT_ID> --format="value(projectNumber)")
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

for secret in DATABASE_URL DATABASE_URL_SYNC; do
  gcloud secrets add-iam-policy-binding ${secret} \
    --project=<PROD_PROJECT_ID> \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/secretmanager.secretAccessor" --quiet

  gcloud secrets add-iam-policy-binding ${secret} \
    --project=<PROD_PROJECT_ID> \
    --member="serviceAccount:${COMPUTE_SA}" \
    --role="roles/secretmanager.secretAccessor" --quiet
done
```

### 7. Actualizar clouddeploy.yaml

Editar el archivo `clouddeploy.yaml` en la raiz del repositorio y reemplazar `<PROJECT_ID>` con el ID real del proyecto de produccion:

```yaml
run:
  location: projects/<PROD_PROJECT_ID>/locations/us-central1
```

### 8. Registrar el pipeline de Cloud Deploy

```bash
gcloud deploy apply --file=clouddeploy.yaml \
  --region=us-central1 \
  --project=<PROD_PROJECT_ID>
```

### 9. Generar clave JSON de la Service Account

```bash
gcloud iam service-accounts keys create key-prod.json \
  --iam-account=github-deploy@<PROD_PROJECT_ID>.iam.gserviceaccount.com
```

---

## Configuracion de GitHub Secrets

Agregar los siguientes secrets en el repositorio de GitHub:

**Settings > Secrets and variables > Actions > New repository secret**

| Secret | Valor | Requerido para |
|--------|-------|----------------|
| `GCP_SA_KEY` | Contenido del archivo `key-dev.json` (o `key-prod.json` si es la misma SA) | Dev y Prod |
| `GCP_PROJECT_ID` | ID del proyecto de produccion (ej. `my-prod-project-123`) | Prod |

### Via CLI

```bash
# Secret de la Service Account
gh secret set GCP_SA_KEY --repo <OWNER>/<REPO> < key-dev.json

# Project ID de produccion
gh secret set GCP_PROJECT_ID --repo <OWNER>/<REPO> --body "<PROD_PROJECT_ID>"
```

> Despues de configurar los secrets, eliminar los archivos `key-dev.json` y `key-prod.json` del disco.

---

## Verificacion

### Verificar que las APIs estan habilitadas

```bash
gcloud services list --enabled --project=<PROJECT_ID> \
  --filter="name:(artifactregistry OR run OR clouddeploy OR secretmanager)"
```

### Verificar la Service Account y sus roles

```bash
gcloud projects get-iam-policy <PROJECT_ID> \
  --flatten="bindings[].members" \
  --filter="bindings.members:github-deploy@" \
  --format="table(bindings.role)"
```

### Verificar los secrets en Secret Manager

```bash
gcloud secrets list --project=<PROJECT_ID> --format="table(name)"
```

### Verificar el pipeline de Cloud Deploy (solo prod)

```bash
gcloud deploy delivery-pipelines describe user-services \
  --region=us-central1 \
  --project=<PROJECT_ID>
```

### Verificar Artifact Registry

```bash
gcloud artifacts repositories describe user-services \
  --location=us-central1 \
  --project=<PROJECT_ID>
```

---

## Flujo CI/CD

### DEV (feature/* y develop)

```
Push -> Tests + Lint -> Build imagen -> Push a Artifact Registry -> gcloud run deploy (directo)
```

- Deploy automatico sin aprobacion
- Variables no sensibles definidas en el workflow (ci.yml)
- Secrets inyectados desde GCP Secret Manager

### PROD (main)

```
Push -> Tests + Lint -> Build imagen -> Push a Artifact Registry -> Cloud Deploy Release
  -> Aprobacion manual -> Canary 10% + verify -> Canary 50% + verify -> Stable 100%
```

- Requiere aprobacion manual en la consola de Cloud Deploy
- Despliegue canary progresivo (10% -> 50% -> 100%)
- Verificacion automatica de salud (/health) entre cada fase
- Rollback automatico si falla la verificacion

### PRs (a main o develop)

```
PR -> Tests + Lint + Docker Build (solo verifica compilacion, no despliega)
```

---

## Troubleshooting

### Error: "Repository not found" al hacer push de imagen

El repositorio de Artifact Registry no existe. Crearlo con:
```bash
gcloud artifacts repositories create user-services \
  --repository-format=docker --location=us-central1 --project=<PROJECT_ID>
```

### Error: "Permission denied" en Secret Manager

La Service Account no tiene acceso a los secrets. Verificar con:
```bash
gcloud secrets get-iam-policy <SECRET_NAME> --project=<PROJECT_ID>
```

### Error: "Container failed startup probe"

La aplicacion no arranca correctamente. Revisar los logs:
```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=user-services" \
  --project=<PROJECT_ID> --limit=20 --format="value(textPayload)"
```

Causas comunes:
- `DATABASE_URL` no configurado o incorrecto
- La base de datos no es accesible desde Cloud Run (revisar VPC connector)
- El puerto no coincide (debe ser 8000)

### Error: "Delivery pipeline not found"

El pipeline de Cloud Deploy no esta registrado. Ejecutar:
```bash
gcloud deploy apply --file=clouddeploy.yaml --region=us-central1 --project=<PROJECT_ID>
```

### Error: "storage.buckets.create denied"

La Service Account necesita el rol `storage.admin`:
```bash
gcloud projects add-iam-policy-binding <PROJECT_ID> \
  --member="serviceAccount:github-deploy@<PROJECT_ID>.iam.gserviceaccount.com" \
  --role="roles/storage.admin" --condition=None --quiet
```

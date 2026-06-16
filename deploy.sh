#!/bin/bash
# deploy.sh — Infraestrutura GCP para o módulo de agendamento do BOB
#
# PRÉ-REQUISITOS (executar antes deste script):
#
#   1. Autenticar com conta Google pessoal:
#        gcloud auth login --no-launch-browser
#
#   2. Copiar credenciais OAuth do YouTube do seu PC local para o servidor:
#        scp config/oauth_client.json campos_1122@IP_SERVIDOR:~/bob/config/
#
#   3. Gerar o token do YouTube (requer navegador — fazer no PC local):
#        python3 -c "from modulos.publicador import yt_autenticar; yt_autenticar()"
#        scp config/youtube_token.json campos_1122@IP_SERVIDOR:~/bob/config/
#
#   4. Confirmar que MONGODB_URI está no .env:
#        grep MONGODB_URI .env
#
# Uso:
#   bash deploy.sh

set -e

# ──────────────────────────────────────────
# Configuração
# ──────────────────────────────────────────
PROJECT_ID="gen-lang-client-0923115995"
REGION="us-east1"
SERVICE_NAME="bob-worker"
BUCKET_NAME="bob-videos-487590427215"
SA_EMAIL="bob-37@${PROJECT_ID}.iam.gserviceaccount.com"
REPO="us-east1-docker.pkg.dev/${PROJECT_ID}/bob"
IMAGE="${REPO}/${SERVICE_NAME}"

echo "======================================"
echo " BOB — Deploy do Módulo de Agendamento"
echo "======================================"
echo " Projeto:  $PROJECT_ID"
echo " Região:   $REGION"
echo " Imagem:   $IMAGE"
echo ""

gcloud config set project $PROJECT_ID --quiet

# ──────────────────────────────────────────
# 1. Habilitar APIs
# ──────────────────────────────────────────
echo "[1/8] Habilitando APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudscheduler.googleapis.com \
  storage.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  --project=$PROJECT_ID

# ──────────────────────────────────────────
# 2. Bucket GCS
# ──────────────────────────────────────────
echo "[2/8] Criando bucket gs://$BUCKET_NAME..."
gsutil ls gs://$BUCKET_NAME 2>/dev/null \
  || gsutil mb -p $PROJECT_ID -l $REGION gs://$BUCKET_NAME

gsutil iam ch serviceAccount:$SA_EMAIL:objectAdmin gs://$BUCKET_NAME
echo "      Bucket OK."

# ──────────────────────────────────────────
# 3. Permissões do Service Account
# ──────────────────────────────────────────
echo "[3/8] Configurando IAM do Service Account..."
for ROLE in \
  "roles/run.invoker" \
  "roles/secretmanager.secretAccessor" \
  "roles/cloudbuild.builds.viewer"; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="$ROLE" \
    --quiet 2>/dev/null || true
done
echo "      IAM OK."

# ──────────────────────────────────────────
# 4. Artifact Registry
# ──────────────────────────────────────────
echo "[4/8] Criando repositório de imagens..."
gcloud artifacts repositories describe bob \
  --repository-format=docker \
  --location=$REGION \
  --project=$PROJECT_ID 2>/dev/null \
  || gcloud artifacts repositories create bob \
    --repository-format=docker \
    --location=$REGION \
    --description="Imagens Docker do BOB" \
    --project=$PROJECT_ID
echo "      Artifact Registry OK."

# ──────────────────────────────────────────
# 5. Secret Manager — MONGODB_URI
# ──────────────────────────────────────────
echo "[5/8] Armazenando MONGODB_URI no Secret Manager..."
MONGODB_URI=$(grep "^MONGODB_URI=" .env | cut -d'=' -f2-)
if [ -z "$MONGODB_URI" ]; then
  echo "ERRO: MONGODB_URI não encontrada no .env"
  echo "      Adicione a linha: MONGODB_URI=mongodb+srv://..."
  exit 1
fi

if gcloud secrets describe mongodb-uri --project=$PROJECT_ID 2>/dev/null; then
  printf '%s' "$MONGODB_URI" | gcloud secrets versions add mongodb-uri \
    --data-file=- --project=$PROJECT_ID
  echo "      Nova versão do secret criada."
else
  printf '%s' "$MONGODB_URI" | gcloud secrets create mongodb-uri \
    --data-file=- --project=$PROJECT_ID
  echo "      Secret criado."
fi

# ──────────────────────────────────────────
# 6. Build via Cloud Build
# ──────────────────────────────────────────
echo "[6/8] Build da imagem Docker via Cloud Build..."
echo "      Isso pode levar 3-5 minutos..."
gcloud builds submit . \
  --config=cloudbuild.yaml \
  --substitutions="_IMAGE=${IMAGE}" \
  --project=$PROJECT_ID
echo "      Build OK — imagem: $IMAGE"

# ──────────────────────────────────────────
# 7. Deploy Cloud Run
# ──────────────────────────────────────────
echo "[7/8] Deploy no Cloud Run..."
gcloud run deploy $SERVICE_NAME \
  --image=$IMAGE \
  --region=$REGION \
  --platform=managed \
  --no-allow-unauthenticated \
  --service-account=$SA_EMAIL \
  --memory=512Mi \
  --cpu=1 \
  --timeout=300 \
  --concurrency=1 \
  --max-instances=1 \
  --set-secrets="MONGODB_URI=mongodb-uri:latest" \
  --set-env-vars="GCS_BUCKET_NAME=$BUCKET_NAME" \
  --project=$PROJECT_ID

WORKER_URL=$(gcloud run services describe $SERVICE_NAME \
  --region=$REGION \
  --project=$PROJECT_ID \
  --format="value(status.url)")
echo "      Worker URL: $WORKER_URL"

# ──────────────────────────────────────────
# 8. Cloud Scheduler
# ──────────────────────────────────────────
echo "[8/8] Configurando Cloud Scheduler (a cada 5 min)..."
if gcloud scheduler jobs describe bob-worker-job \
  --location=$REGION --project=$PROJECT_ID 2>/dev/null; then
  gcloud scheduler jobs update http bob-worker-job \
    --location=$REGION \
    --schedule="*/5 * * * *" \
    --uri="${WORKER_URL}/" \
    --http-method=POST \
    --oidc-service-account-email=$SA_EMAIL \
    --project=$PROJECT_ID
  echo "      Job atualizado."
else
  gcloud scheduler jobs create http bob-worker-job \
    --location=$REGION \
    --schedule="*/5 * * * *" \
    --uri="${WORKER_URL}/" \
    --http-method=POST \
    --oidc-service-account-email=$SA_EMAIL \
    --project=$PROJECT_ID
  echo "      Job criado."
fi

# ──────────────────────────────────────────
# Resumo
# ──────────────────────────────────────────
echo ""
echo "======================================"
echo " Deploy concluído com sucesso!"
echo "======================================"
echo ""
echo " Worker URL : $WORKER_URL"
echo " Bucket     : gs://$BUCKET_NAME"
echo " Scheduler  : a cada 5 minutos"
echo ""
echo " Testar manualmente:"
echo "   gcloud scheduler jobs run bob-worker-job --location=$REGION"
echo ""
echo " Ver logs:"
echo "   gcloud run services logs read $SERVICE_NAME --region=$REGION --limit=50"
echo ""

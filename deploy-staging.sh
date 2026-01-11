#!/bin/bash
# Deploy to Cloud Run (staging/test)
# Usage: ./deploy-staging.sh [app_name]
# Default app name: imagination-map-staging

APP_NAME="${1:-imagination-map-staging}"
PROJECT_ID="jupyterhub-379311"
REGION="europe-north1"

echo "🚀 Starting staging deployment for $APP_NAME"

# Build the Docker image
echo "📦 Building Docker image..."
docker build --no-cache -t $APP_NAME .

# Tag the image for Google Container Registry
echo "🏷️ Tagging image for GCR..."
docker tag $APP_NAME gcr.io/$PROJECT_ID/$APP_NAME

# Push to Google Container Registry
echo "⬆️ Pushing to Google Container Registry..."
docker push gcr.io/$PROJECT_ID/$APP_NAME

# Deploy to Cloud Run with modest staging resources
echo "🌩️ Deploying to Cloud Run (staging)..."
gcloud run deploy $APP_NAME \
  --image gcr.io/$PROJECT_ID/$APP_NAME \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --set-env-vars APP_NAME=$APP_NAME,ENVIRONMENT=production \
  --memory 1Gi \
  --cpu 1 \
  --concurrency 20 \
  --timeout 3600

echo "✅ Deployment complete!"
echo "Staging URL (if using dh.nb.no proxy): dh.nb.no/run/$APP_NAME/"
echo ""
echo "Logs: gcloud run services logs read $APP_NAME --region $REGION"
echo "Local debug: docker run -p 8080:8080 -e APP_NAME=$APP_NAME -e ENVIRONMENT=production $APP_NAME"

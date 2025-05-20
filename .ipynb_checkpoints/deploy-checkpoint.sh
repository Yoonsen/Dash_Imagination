#!/bin/bash
# Deploy script for Google Cloud Run
# Usage: ./deploy.sh <app_name>

# Check if app name is provided
if [ -z "$1" ]
then
    echo "Please provide an app name"
    echo "Usage: ./deploy.sh <app_name>"
    exit 1
fi

APP_NAME=$1
PROJECT_ID="jupyterhub-379311"
REGION="europe-north1"

echo "🚀 Starting deployment pipeline for $APP_NAME"

# Build the Docker image
echo "📦 Building Docker image..."
docker build -t $APP_NAME . --no-cache

# Tag the image for Google Container Registry
echo "🏷️ Tagging image for GCR..."
docker tag $APP_NAME gcr.io/$PROJECT_ID/$APP_NAME

# Push to Google Container Registry
echo "⬆️ Pushing to Google Container Registry..."
docker push gcr.io/$PROJECT_ID/$APP_NAME

# Deploy to Cloud Run
echo "🌩️ Deploying to Cloud Run..."
gcloud run deploy $APP_NAME \
  --image gcr.io/$PROJECT_ID/$APP_NAME \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --set-env-vars APP_NAME=$APP_NAME,ENVIRONMENT=production \
  --memory 512Mi \
  --timeout 3600 \
  --cpu 1

echo "✅ Deployment complete!"
echo "Your app should be available at: dh.nb.no/run/$APP_NAME/"
echo ""
echo "❓ If the deployment fails, check the logs with:"
echo "gcloud run services logs read $APP_NAME --region $REGION"
echo ""
echo "🔍 You can also debug the container locally with:"
echo "docker run -p 8080:8080 -e APP_NAME=$APP_NAME -e ENVIRONMENT=production $APP_NAME"
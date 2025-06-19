#!/bin/bash

# Configuration
SERVICE_NAME="adk-unity-service"
REGION="us-central1"
PROJECT_ID=$(gcloud config get-value project)
BUCKET_NAME="my_adk_unity_hackathon_builds_2025"

echo "Deploying Cloud Run service..."

# Path to your .env file inside the subfolder
ENV_PATH="multi_tool_agent/.env"

# Load .env variables from that path
ENV_VARS=$(grep -v '^#' "$ENV_PATH" | xargs | sed 's/ /,/g')

# Deploy to Cloud Run
gcloud run deploy $SERVICE_NAME \
  --image gcr.io/$PROJECT_ID/adk-unity-agent:latest \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --set-env-vars=PYTHONPATH=/app/multi_tool_agent/my_google_adk:/app,${ENV_VARS},APP_BASE_URL=https://adk-unity-service-106481734717.us-central1.run.app \
  --timeout 300s


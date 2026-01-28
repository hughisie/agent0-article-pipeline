#!/bin/bash

# Deployment script for Google Cloud Run
# This script deploys the Agent0 GUI to Google Cloud Run

set -e

# Configuration
PROJECT_ID="519332615404"
REGION="us-central1"
SERVICE_NAME="agent0-gui"
DRIVE_FOLDER_ID="17txivAocXR4R5qMsWi4vYUB6Kg2K1N1m"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting deployment to Google Cloud Run...${NC}"

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}Error: gcloud CLI is not installed${NC}"
    echo "Please install it from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Set project
echo -e "${YELLOW}Setting project to ${PROJECT_ID}...${NC}"
gcloud config set project ${PROJECT_ID}

# Enable required APIs
echo -e "${YELLOW}Enabling required Google Cloud APIs...${NC}"
gcloud services enable cloudbuild.googleapis.com \
    run.googleapis.com \
    containerregistry.googleapis.com \
    secretmanager.googleapis.com \
    drive.googleapis.com

# Build and deploy using Cloud Build
echo -e "${YELLOW}Building and deploying using Cloud Build...${NC}"
gcloud builds submit --config cloudbuild.yaml

echo -e "${GREEN}Deployment complete!${NC}"
echo ""
echo -e "${GREEN}Your application is now running at:${NC}"
gcloud run services describe ${SERVICE_NAME} --region=${REGION} --format='value(status.url)'
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Set up secrets in Google Cloud Secret Manager (see DEPLOYMENT.md)"
echo "2. Configure OAuth credentials in Google Cloud Console"
echo "3. Update your OAuth redirect URIs"

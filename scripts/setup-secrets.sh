#!/bin/bash

# Script to set up Google Cloud secrets
# Run this script to create all required secrets in Google Secret Manager

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}Google Cloud Secret Setup${NC}"
echo "This script will guide you through creating secrets in Google Secret Manager"
echo ""

# Set project
PROJECT_ID="519332615404"
gcloud config set project ${PROJECT_ID}

echo -e "${YELLOW}Creating secrets...${NC}"
echo ""

# Function to create or update secret
create_secret() {
    local SECRET_NAME=$1
    local PROMPT=$2
    
    echo -e "${YELLOW}${PROMPT}${NC}"
    read -r SECRET_VALUE
    
    if [ -z "$SECRET_VALUE" ]; then
        echo -e "${RED}Skipping ${SECRET_NAME} (empty value)${NC}"
        return
    fi
    
    # Check if secret exists
    if gcloud secrets describe ${SECRET_NAME} &>/dev/null; then
        echo -n "$SECRET_VALUE" | gcloud secrets versions add ${SECRET_NAME} --data-file=-
        echo -e "${GREEN}✓ Updated ${SECRET_NAME}${NC}"
    else
        echo -n "$SECRET_VALUE" | gcloud secrets create ${SECRET_NAME} --data-file=-
        echo -e "${GREEN}✓ Created ${SECRET_NAME}${NC}"
    fi
    echo ""
}

# Create all secrets
create_secret "GEMINI_API_KEY" "Enter your Gemini API key:"
create_secret "DEEPSEEK_API_KEY" "Enter your DeepSeek API key (optional, press Enter to skip):"
create_secret "WP_BASE_URL" "Enter your WordPress base URL (e.g., https://example.com):"
create_secret "WP_USERNAME" "Enter your WordPress username:"
create_secret "WP_APPLICATION_PASSWORD" "Enter your WordPress application password:"
create_secret "GOOGLE_CLIENT_ID" "Enter your Google OAuth Client ID:"

# Generate JWT secret
echo -e "${YELLOW}Generating JWT secret...${NC}"
JWT_SECRET=$(openssl rand -hex 32)
echo -n "$JWT_SECRET" | gcloud secrets create JWT_SECRET --data-file=- 2>/dev/null || \
    echo -n "$JWT_SECRET" | gcloud secrets versions add JWT_SECRET --data-file=-
echo -e "${GREEN}✓ Generated and saved JWT_SECRET${NC}"
echo ""

create_secret "GOOGLE_ACCESS_TOKEN" "Enter your Google access token (for Drive API, press Enter to skip for now):"

echo ""
echo -e "${GREEN}Granting Cloud Run access to secrets...${NC}"

# Get service account
PROJECT_NUMBER=$(gcloud projects describe ${PROJECT_ID} --format="value(projectNumber)")
SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

# Grant access to each secret
for SECRET in GEMINI_API_KEY DEEPSEEK_API_KEY WP_BASE_URL WP_USERNAME WP_APPLICATION_PASSWORD GOOGLE_CLIENT_ID JWT_SECRET GOOGLE_ACCESS_TOKEN; do
    if gcloud secrets describe ${SECRET} &>/dev/null; then
        gcloud secrets add-iam-policy-binding ${SECRET} \
            --member="serviceAccount:${SERVICE_ACCOUNT}" \
            --role="roles/secretmanager.secretAccessor" &>/dev/null
        echo -e "${GREEN}✓ Granted access to ${SECRET}${NC}"
    fi
done

echo ""
echo -e "${GREEN}✅ Secret setup complete!${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Run ./deploy.sh to deploy to Google Cloud Run"
echo "2. Get your service URL: gcloud run services describe agent0-gui --region=us-central1 --format='value(status.url)'"
echo "3. Update OAuth redirect URIs with your service URL"

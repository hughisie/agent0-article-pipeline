# Google Cloud Deployment Guide

This guide explains how to deploy the Agent0 GUI application to Google Cloud Run with OAuth and Google Drive integration.

## Prerequisites

- Google Cloud account with billing enabled
- Project ID: `519332615404`
- gcloud CLI installed ([Installation Guide](https://cloud.google.com/sdk/docs/install))
- Git repository connected to GitHub (for auto-deployment)

## Architecture

The application is deployed as a containerized service on Google Cloud Run with:
- **Authentication**: Google OAuth 2.0 for user login
- **Storage**: Google Drive API for file management
- **Secrets**: Google Secret Manager for secure credential storage
- **Auto-deployment**: GitHub Actions workflow on push to main branch

## Initial Setup

### 1. Install gcloud CLI

```bash
# Install gcloud CLI (macOS)
brew install google-cloud-sdk

# Or download from:
# https://cloud.google.com/sdk/docs/install

# Authenticate
gcloud auth login

# Set project
gcloud config set project 519332615404
```

### 2. Enable Required Google Cloud APIs

```bash
gcloud services enable cloudbuild.googleapis.com \
    run.googleapis.com \
    containerregistry.googleapis.com \
    secretmanager.googleapis.com \
    drive.googleapis.com \
    iamcredentials.googleapis.com
```

### 3. Create OAuth 2.0 Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to **APIs & Services > Credentials**
3. Click **Create Credentials > OAuth 2.0 Client ID**
4. Application type: **Web application**
5. Name: `Agent0 GUI`
6. Authorized JavaScript origins:
   - `https://agent0-gui-<hash>.run.app` (get this after first deployment)
   - `http://localhost:9000` (for local development)
7. Authorized redirect URIs:
   - `https://agent0-gui-<hash>.run.app/auth/callback`
   - `http://localhost:9000/auth/callback`
8. Save the **Client ID** and **Client Secret**

### 4. Enable Google Drive API

1. Go to **APIs & Services > Library**
2. Search for "Google Drive API"
3. Click **Enable**
4. Create a service account or use user OAuth (recommended: user OAuth for Drive access)

### 5. Set Up Google Drive Folder Permissions

1. Open the Google Drive folder: https://drive.google.com/drive/folders/17txivAocXR4R5qMsWi4vYUB6Kg2K1N1m
2. Share the folder with your OAuth email or service account
3. Grant "Viewer" or "Editor" permissions

### 6. Create Secrets in Google Secret Manager

```bash
# Create secrets for sensitive data
echo -n "your-gemini-api-key" | gcloud secrets create GEMINI_API_KEY --data-file=-
echo -n "your-deepseek-api-key" | gcloud secrets create DEEPSEEK_API_KEY --data-file=-
echo -n "https://your-wordpress-site.com" | gcloud secrets create WP_BASE_URL --data-file=-
echo -n "your-wp-username" | gcloud secrets create WP_USERNAME --data-file=-
echo -n "your-wp-app-password" | gcloud secrets create WP_APPLICATION_PASSWORD --data-file=-
echo -n "your-google-oauth-client-id" | gcloud secrets create GOOGLE_CLIENT_ID --data-file=-
echo -n "$(openssl rand -hex 32)" | gcloud secrets create JWT_SECRET --data-file=-

# For Google Drive access token (generate from OAuth flow)
echo -n "your-google-access-token" | gcloud secrets create GOOGLE_ACCESS_TOKEN --data-file=-
```

### 7. Grant Cloud Run Access to Secrets

```bash
# Get the Cloud Run service account email
PROJECT_NUMBER=$(gcloud projects describe 519332615404 --format="value(projectNumber)")
SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

# Grant access to each secret
for SECRET in GEMINI_API_KEY DEEPSEEK_API_KEY WP_BASE_URL WP_USERNAME WP_APPLICATION_PASSWORD GOOGLE_CLIENT_ID JWT_SECRET GOOGLE_ACCESS_TOKEN; do
    gcloud secrets add-iam-policy-binding $SECRET \
        --member="serviceAccount:${SERVICE_ACCOUNT}" \
        --role="roles/secretmanager.secretAccessor"
done
```

## Deployment Methods

### Method 1: Manual Deployment (Recommended for First Deploy)

```bash
# Make the deploy script executable
chmod +x deploy.sh

# Run deployment
./deploy.sh
```

### Method 2: Using Cloud Build Directly

```bash
gcloud builds submit --config cloudbuild.yaml
```

### Method 3: GitHub Actions (Automatic)

1. **Create a Service Account for GitHub Actions**:

```bash
gcloud iam service-accounts create github-actions \
    --display-name="GitHub Actions Deployment"

gcloud projects add-iam-policy-binding 519332615404 \
    --member="serviceAccount:github-actions@519332615404.iam.gserviceaccount.com" \
    --role="roles/run.admin"

gcloud projects add-iam-policy-binding 519332615404 \
    --member="serviceAccount:github-actions@519332615404.iam.gserviceaccount.com" \
    --role="roles/storage.admin"

gcloud projects add-iam-policy-binding 519332615404 \
    --member="serviceAccount:github-actions@519332615404.iam.gserviceaccount.com" \
    --role="roles/iam.serviceAccountUser"

# Create and download key
gcloud iam service-accounts keys create github-actions-key.json \
    --iam-account=github-actions@519332615404.iam.gserviceaccount.com
```

2. **Add Secret to GitHub**:
   - Go to your GitHub repository
   - Navigate to **Settings > Secrets and variables > Actions**
   - Click **New repository secret**
   - Name: `GCP_SA_KEY`
   - Value: Contents of `github-actions-key.json`

3. **Enable Auto-Deployment**:
   - Push to `main` or `production` branch
   - GitHub Actions will automatically build and deploy

## Syncing Local Changes to Cloud

The GitHub Actions workflow ensures that any changes you push to the `main` branch are automatically deployed to Google Cloud Run. This keeps both instances in sync.

### Workflow:

1. Make changes locally
2. Test locally: `uvicorn agent0_gui.app:app --reload --port 9000`
3. Commit and push:
   ```bash
   git add .
   git commit -m "Your change description"
   git push origin main
   ```
4. GitHub Actions automatically deploys to Cloud Run (takes ~5-10 minutes)

### Monitor Deployment:

- **GitHub**: Check Actions tab for deployment status
- **Google Cloud Console**: Navigate to Cloud Run > agent0-gui
- **Logs**: `gcloud run services logs read agent0-gui --region=us-central1`

## Accessing the Application

After deployment:

```bash
# Get the service URL
gcloud run services describe agent0-gui --region=us-central1 --format='value(status.url)'
```

Visit the URL to access your application.

## OAuth Flow Setup

1. **Update OAuth Redirect URIs** with your Cloud Run URL:
   - Go to Google Cloud Console > APIs & Services > Credentials
   - Edit your OAuth 2.0 Client ID
   - Add: `https://your-cloud-run-url/auth/callback`

2. **Test Authentication**:
   - Visit your Cloud Run URL
   - Click "Sign in with Google"
   - Authorize the application
   - You should be redirected back with authentication

## Google Drive Integration

The application connects to folder ID: `17txivAocXR4R5qMsWi4vYUB6Kg2K1N1m`

### Using Google Drive Files:

1. Sign in with your Google account
2. Navigate to the "Drive Files" section in the UI
3. Browse files in the configured folder
4. Select files to download and process
5. Files are automatically downloaded to the workspace

### Generating Google Access Token:

For production use, implement OAuth flow to get user's Drive access token:

```python
# This is handled by the OAuth flow in the application
# User signs in with Google -> gets access token -> stored in session
```

## Managing Secrets

### Update a Secret:

```bash
echo -n "new-secret-value" | gcloud secrets versions add SECRET_NAME --data-file=-
```

### List Secrets:

```bash
gcloud secrets list
```

### View Secret Value (for debugging):

```bash
gcloud secrets versions access latest --secret="SECRET_NAME"
```

## Monitoring and Logs

### View Application Logs:

```bash
# Real-time logs
gcloud run services logs tail agent0-gui --region=us-central1

# Recent logs
gcloud run services logs read agent0-gui --region=us-central1 --limit=100
```

### View Deployment Status:

```bash
gcloud run services describe agent0-gui --region=us-central1
```

### Monitor Resource Usage:

Visit: https://console.cloud.google.com/run/detail/us-central1/agent0-gui/metrics?project=519332615404

## Cost Management

Google Cloud Run free tier includes:
- 2 million requests per month
- 360,000 GB-seconds of memory
- 180,000 vCPU-seconds

With current configuration (2GB RAM, 2 CPU):
- **Always free**: ~40 hours/month
- **Beyond free tier**: ~$0.48/hour

To minimize costs:
- `min-instances: 0` (scales to zero when idle)
- Monitor usage in Cloud Console

## Troubleshooting

### Build Fails

```bash
# Check build logs
gcloud builds list --limit=5
gcloud builds log <BUILD_ID>
```

### Deployment Fails

```bash
# Check service status
gcloud run services describe agent0-gui --region=us-central1

# Check logs
gcloud run services logs read agent0-gui --region=us-central1 --limit=50
```

### OAuth Not Working

1. Verify GOOGLE_CLIENT_ID secret is correct
2. Check redirect URIs match exactly (including https://)
3. Ensure Drive API is enabled
4. Check user has access to the Drive folder

### Secrets Not Loading

```bash
# Verify service account has access
gcloud secrets get-iam-policy SECRET_NAME

# Test secret access
gcloud secrets versions access latest --secret="SECRET_NAME"
```

## Rollback

### Rollback to Previous Deployment:

```bash
# List revisions
gcloud run revisions list --service=agent0-gui --region=us-central1

# Rollback to specific revision
gcloud run services update-traffic agent0-gui \
    --to-revisions=REVISION_NAME=100 \
    --region=us-central1
```

## Local Development with Cloud Secrets

```bash
# Download secrets for local development
gcloud secrets versions access latest --secret="GEMINI_API_KEY" > .env
echo "DEEPSEEK_API_KEY=$(gcloud secrets versions access latest --secret=DEEPSEEK_API_KEY)" >> .env
echo "GOOGLE_CLIENT_ID=$(gcloud secrets versions access latest --secret=GOOGLE_CLIENT_ID)" >> .env
# ... add other secrets

# Load in your terminal
export $(cat .env | xargs)

# Run locally
uvicorn agent0_gui.app:app --reload --port 9000
```

## Security Best Practices

1. **Never commit secrets** to Git (use .gitignore)
2. **Rotate secrets** regularly
3. **Use least privilege** for service accounts
4. **Enable Cloud Armor** for DDoS protection (if needed)
5. **Monitor access logs** regularly
6. **Use VPC** if connecting to private resources

## Support

- **Google Cloud Documentation**: https://cloud.google.com/run/docs
- **Issue Tracker**: Create GitHub issues for bugs
- **Logs**: Check Cloud Run logs for detailed error messages

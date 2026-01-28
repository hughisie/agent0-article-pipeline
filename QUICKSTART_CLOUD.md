# Quick Start: Deploy to Google Cloud

## TL;DR - Fast Deployment

```bash
# 1. Install gcloud (if not installed)
brew install google-cloud-sdk

# 2. Authenticate and set project
gcloud auth login
gcloud config set project 519332615404

# 3. Enable APIs
gcloud services enable cloudbuild.googleapis.com run.googleapis.com \
    containerregistry.googleapis.com secretmanager.googleapis.com drive.googleapis.com

# 4. Create secrets (replace with your actual values)
echo -n "YOUR_GEMINI_KEY" | gcloud secrets create GEMINI_API_KEY --data-file=-
echo -n "YOUR_DEEPSEEK_KEY" | gcloud secrets create DEEPSEEK_API_KEY --data-file=-
echo -n "https://your-site.com" | gcloud secrets create WP_BASE_URL --data-file=-
echo -n "wp_user" | gcloud secrets create WP_USERNAME --data-file=-
echo -n "wp_app_pass" | gcloud secrets create WP_APPLICATION_PASSWORD --data-file=-
echo -n "YOUR_GOOGLE_CLIENT_ID" | gcloud secrets create GOOGLE_CLIENT_ID --data-file=-
echo -n "$(openssl rand -hex 32)" | gcloud secrets create JWT_SECRET --data-file=-
echo -n "YOUR_ACCESS_TOKEN" | gcloud secrets create GOOGLE_ACCESS_TOKEN --data-file=-

# 5. Grant Cloud Run access to secrets
PROJECT_NUMBER=$(gcloud projects describe 519332615404 --format="value(projectNumber)")
SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

for SECRET in GEMINI_API_KEY DEEPSEEK_API_KEY WP_BASE_URL WP_USERNAME \
    WP_APPLICATION_PASSWORD GOOGLE_CLIENT_ID JWT_SECRET GOOGLE_ACCESS_TOKEN; do
    gcloud secrets add-iam-policy-binding $SECRET \
        --member="serviceAccount:${SERVICE_ACCOUNT}" \
        --role="roles/secretmanager.secretAccessor"
done

# 6. Deploy
./deploy.sh

# 7. Get your app URL
gcloud run services describe agent0-gui --region=us-central1 --format='value(status.url)'
```

## OAuth Setup (Required for Google Sign-In)

1. Go to: https://console.cloud.google.com/apis/credentials?project=519332615404
2. Click **Create Credentials > OAuth 2.0 Client ID**
3. Application type: **Web application**
4. Name: `Agent0 GUI`
5. **Authorized JavaScript origins**:
   - Get your Cloud Run URL from step 7 above
   - Add: `https://your-cloud-run-url`
   - Add: `http://localhost:9000` (for local dev)
6. **Authorized redirect URIs**:
   - Add: `https://your-cloud-run-url/auth/callback`
   - Add: `http://localhost:9000/auth/callback`
7. Copy the **Client ID** and update the secret:
   ```bash
   echo -n "your-client-id" | gcloud secrets versions add GOOGLE_CLIENT_ID --data-file=-
   ```

## Google Drive Access

Your app is configured to access folder: `17txivAocXR4R5qMsWi4vYUB6Kg2K1N1m`

**Option 1: Service Account (Recommended)**
```bash
# Create service account
gcloud iam service-accounts create drive-access --display-name="Drive Access"

# Generate key
gcloud iam service-accounts keys create drive-key.json \
    --iam-account=drive-access@519332615404.iam.gserviceaccount.com

# Share the Drive folder with: drive-access@519332615404.iam.gserviceaccount.com
```

**Option 2: OAuth User Token**
- Users authenticate with their Google account
- Access token is obtained through OAuth flow
- No manual token management needed

## Auto-Deploy with GitHub Actions

1. **Create service account for GitHub**:
```bash
gcloud iam service-accounts create github-actions --display-name="GitHub Actions"

gcloud projects add-iam-policy-binding 519332615404 \
    --member="serviceAccount:github-actions@519332615404.iam.gserviceaccount.com" \
    --role="roles/run.admin"

gcloud projects add-iam-policy-binding 519332615404 \
    --member="serviceAccount:github-actions@519332615404.iam.gserviceaccount.com" \
    --role="roles/storage.admin"

gcloud projects add-iam-policy-binding 519332615404 \
    --member="serviceAccount:github-actions@519332615404.iam.gserviceaccount.com" \
    --role="roles/iam.serviceAccountUser"

gcloud iam service-accounts keys create github-key.json \
    --iam-account=github-actions@519332615404.iam.gserviceaccount.com
```

2. **Add to GitHub Secrets**:
   - Go to your repo → Settings → Secrets and variables → Actions
   - Click **New repository secret**
   - Name: `GCP_SA_KEY`
   - Value: Paste contents of `github-key.json`

3. **Push to deploy**:
```bash
git add .
git commit -m "Deploy to Cloud Run"
git push origin main
```

GitHub will automatically build and deploy on every push to `main`!

## Verify Deployment

```bash
# Check service status
gcloud run services describe agent0-gui --region=us-central1

# View logs
gcloud run services logs tail agent0-gui --region=us-central1

# Get service URL
gcloud run services describe agent0-gui --region=us-central1 --format='value(status.url)'
```

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables (use your local values or download from secrets)
export GOOGLE_CLIENT_ID="your-client-id"
export GEMINI_API_KEY="your-key"
export DEEPSEEK_API_KEY="your-key"
# ... etc

# Run locally
uvicorn agent0_gui.app:app --reload --port 9000

# Visit: http://localhost:9000
```

## Sync Local Changes to Cloud

Every push to `main` branch automatically deploys to Cloud Run:

```bash
# 1. Make changes locally
# 2. Test locally
# 3. Commit and push
git add .
git commit -m "Your changes"
git push origin main

# 4. GitHub Actions deploys automatically (takes ~5-10 min)
# 5. Both local and cloud are now in sync
```

## Monitor Deployment

- **GitHub Actions**: https://github.com/your-repo/actions
- **Cloud Console**: https://console.cloud.google.com/run/detail/us-central1/agent0-gui?project=519332615404
- **Logs**: `gcloud run services logs read agent0-gui --region=us-central1`

## Troubleshooting

**Build fails?**
```bash
gcloud builds list --limit=5
gcloud builds log <BUILD_ID>
```

**Service not starting?**
```bash
gcloud run services logs read agent0-gui --region=us-central1 --limit=50
```

**Secrets not loading?**
```bash
# Test secret access
gcloud secrets versions access latest --secret="GEMINI_API_KEY"
```

**OAuth not working?**
- Check GOOGLE_CLIENT_ID is correct
- Verify redirect URIs match exactly
- Ensure Drive API is enabled

## Cost Estimate

**Free tier** (per month):
- 2M requests
- 360,000 GB-seconds memory
- 180,000 vCPU-seconds

**Current config** (2GB RAM, 2 CPU):
- ~40 hours/month free
- Beyond free tier: ~$0.48/hour

With `min-instances: 0`, the service scales to zero when idle → **minimal costs**

## Next Steps

1. ✅ Deploy to Cloud Run
2. ✅ Set up OAuth credentials
3. ✅ Test Google Sign-In
4. ✅ Test Google Drive file browser
5. ✅ Push to GitHub for auto-deploy
6. 🎉 Done!

For detailed documentation, see [DEPLOYMENT.md](./DEPLOYMENT.md)

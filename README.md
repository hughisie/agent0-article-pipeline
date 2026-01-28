# Agent0 - Article Translation & Publishing Pipeline

A comprehensive system for extracting, translating, sourcing, and publishing articles to WordPress with Google Drive integration.

## Features

- 📁 **File Upload & Scanning** - Upload directories of articles (.json, .md, .markdown)
- 🌍 **Translation** - Automatic headline translation to English (GB)
- 🔍 **Source Finding** - AI-powered primary source discovery
- ✍️ **Article Enhancement** - Rewrite and enhance articles with AI
- 📝 **WordPress Publishing** - Direct publishing to WordPress as drafts
- 💾 **Google Drive Integration** - Backup and sync with Google Drive
- 🎯 **Profile Management** - Multiple writing profiles with custom prompts
- 📊 **Real-time Progress** - Live status updates during uploads and processing

## Recent Improvements (Jan 2026)

✅ **Enhanced Upload & Scan Status Tracking**
- Real-time progress indicators with visual feedback
- Comprehensive logging throughout upload and scan processes
- Detailed error messages with debugging hints
- Console logging for troubleshooting (press F12 in browser)
- Better handling of partial failures

See `UPLOAD_SCAN_STATUS_IMPROVEMENTS.md` for detailed documentation.

## Quick Start

### Prerequisites

- Python 3.11 or higher
- Node.js 18 or higher (for frontend)
- Google Cloud account (for deployment)
- WordPress site with REST API enabled
- DeepSeek API key (for translation)

### Setup on a New Computer

1. **Clone the repository:**
   ```bash
   git clone <your-repo-url>
   cd "Extract'n'Source'n'Write'n'Enhance'n'publish"
   ```

2. **Set up Python virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Install frontend dependencies:**
   ```bash
   cd agent0_gui/web
   npm install
   npm run build
   cd ../..
   ```

4. **Configure the application:**
   
   Create `config.json` in the root directory:
   ```json
   {
     "deepseek_api_key": "your-deepseek-api-key",
     "wordpress_url": "https://your-site.com",
     "wordpress_username": "your-username",
     "wordpress_app_password": "your-app-password"
   }
   ```

5. **Set up Google Drive (optional):**
   
   Place your `drive-key.json` in the root directory (get from Google Cloud Console).

6. **Run the application:**
   ```bash
   source venv/bin/activate
   uvicorn agent0_gui.app:app --host 0.0.0.0 --port 8000
   ```

7. **Open in browser:**
   ```
   http://localhost:8000
   ```

## Project Structure

```
.
├── agent0.py                    # Main pipeline orchestrator
├── agent0_scanner.py            # Directory scanning with progress callbacks
├── agent0_translator.py         # Translation service
├── agent0_sourcer.py           # Primary source finder
├── agent0_writer.py            # Article enhancement
├── agent0_publisher.py         # WordPress publishing
├── agent0_gui/                 # Web interface
│   ├── app.py                  # FastAPI backend
│   ├── web/                    # React frontend
│   │   ├── src/
│   │   └── package.json
│   ├── scanner.py              # GUI-specific scanning
│   ├── db.py                   # Database operations
│   └── workspace/              # Upload storage (gitignored)
├── config.json                 # Configuration (gitignored)
├── requirements.txt            # Python dependencies
├── deploy.sh                   # Google Cloud deployment script
└── README.md                   # This file
```

## Usage

### Upload Files for Translation

1. Click **"Choose folder(s)"** in the web interface
2. Select a directory containing article files
3. Watch the real-time progress indicators:
   - 🔵 Blue spinner = Upload/scan in progress
   - ✅ Green box = Success with file count
   - ❌ Red box = Error with details
   - ⚠️ Amber box = Warning (partial success)

### Process Articles

1. **Scan** - Articles are automatically scanned after upload
2. **Translate** - Click "Translate Headlines" to translate to English
3. **Source** - Click "Find Sources" to discover primary sources
4. **Enhance** - Click "Rewrite & Enhance" to improve articles
5. **Publish** - Click "Build & Publish to WordPress" to create drafts

### Quick Article Creation

Use the "Quick Article" feature to create articles from text or URLs directly.

### Profile Management

Create multiple writing profiles with custom prompts for different writing styles or publications.

## Deployment to Google Cloud Run

1. **Configure deployment:**
   
   Edit `deploy.sh` with your project details:
   ```bash
   PROJECT_ID="your-project-id"
   REGION="us-central1"
   SERVICE_NAME="agent0-gui"
   ```

2. **Deploy:**
   ```bash
   ./deploy.sh
   ```

3. **Set up secrets in Google Cloud:**
   - DeepSeek API key
   - WordPress credentials
   - Google Drive credentials

See `DEPLOYMENT.md` for detailed deployment instructions.

## Debugging

### Upload Issues

1. **Check browser console** (F12 → Console tab)
   - Look for `[UPLOAD]` and `[PICKER]` messages
   - Check for JavaScript errors

2. **Check server logs**
   - Look for `[UPLOAD]`, `[RESCAN]`, and `[SCAN]` messages
   - Verify files were saved to disk

3. **Verify file types**
   - Only `.json`, `.md`, and `.markdown` files are processed

### Common Issues

**"No files uploaded"**
- Ensure directory contains .json, .md, or .markdown files

**"Upload succeeded but no articles shown"**
- Check server logs for scan errors
- Verify file permissions

**"Symlink failed" in logs**
- Normal on Windows or some cloud environments
- System automatically falls back to copy

## API Endpoints

- `POST /api/upload` - Upload files
- `POST /api/rescan` - Rescan directories
- `POST /api/translate` - Translate headlines
- `POST /api/source` - Find primary sources
- `POST /api/enhance` - Enhance articles
- `POST /api/publish` - Publish to WordPress
- `GET /api/settings` - Get settings
- `POST /api/settings` - Update settings

## Configuration

### Environment Variables

- `DEEPSEEK_API_KEY` - DeepSeek API key for translation
- `WORKSPACE_ROOT` - Root directory for uploads (default: `agent0_gui/workspace`)
- `PORT` - Server port (default: 8000)

### Config File (`config.json`)

```json
{
  "deepseek_api_key": "sk-...",
  "wordpress_url": "https://your-site.com",
  "wordpress_username": "admin",
  "wordpress_app_password": "xxxx xxxx xxxx xxxx",
  "google_drive_folder_id": "your-folder-id",
  "default_profile": "default"
}
```

## Development

### Run in Development Mode

**Backend:**
```bash
source venv/bin/activate
uvicorn agent0_gui.app:app --reload --host 0.0.0.0 --port 8000
```

**Frontend:**
```bash
cd agent0_gui/web
npm run dev
```

### Run Tests

```bash
pytest
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

[Your License Here]

## Support

For issues or questions:
- Check `UPLOAD_SCAN_STATUS_IMPROVEMENTS.md` for upload/scan troubleshooting
- Review server logs for detailed error messages
- Open browser console (F12) for frontend debugging

## Changelog

See `UPLOAD_SCAN_STATUS_IMPROVEMENTS.md` for recent improvements to upload and scan functionality.

# Multi-Profile System Guide

## Overview

The Agent0 GUI now supports multiple profiles, allowing you to process different types of articles (like Barcelona news, retro games, etc.) with separate configurations. Each profile has:

- **Custom Input/Output Directories**: Separate folders for reading source articles and saving output
- **Custom LLM Prompts**: Full control over every prompt used in the article processing pipeline
- **Independent Settings**: Each profile can have its own configuration

## Features Implemented

### 1. Database Schema

**New Tables:**
- `profiles`: Stores profile information (name, directories, active status)
- `profile_prompts`: Stores custom prompts for each profile

**Default Profile:**
- A "Default" profile is automatically created on first run
- Uses directories: `current` (input) and `output` (output)

### 2. Backend API Endpoints

**Profile Management:**
- `GET /api/profiles` - List all profiles
- `GET /api/profiles/active` - Get active profile with directories
- `GET /api/profiles/{id}` - Get specific profile
- `POST /api/profiles` - Create new profile
- `PUT /api/profiles/{id}` - Update profile
- `DELETE /api/profiles/{id}` - Delete profile (cannot delete active)
- `POST /api/profiles/{id}/activate` - Set profile as active

**Prompt Management:**
- `GET /api/prompts/keys` - List all available prompt keys
- `GET /api/profiles/{id}/prompts` - Get all prompts for profile
- `PUT /api/profiles/{id}/prompts/{key}` - Update custom prompt
- `DELETE /api/profiles/{id}/prompts/{key}` - Reset prompt to default

### 3. Prompt System Enhancement

**Available Prompts:**
1. **Translation & Analysis**
   - `PROMPT_TRANSLATION_SYSTEM` - System prompt for translation
   - `PROMPT_TRANSLATION_USER` - User prompt for translation

2. **Primary Source Finding**
   - `PROMPT_PRIMARY_SYSTEM` - System prompt for finding sources
   - `PROMPT_PRIMARY_USER` - User prompt for source validation

3. **Article Writing**
   - `PROMPT_ARTICLE_SYSTEM` - System prompt for article generation
   - `PROMPT_ARTICLE_USER` - User prompt for article structure

4. **Related Articles**
   - `PROMPT_RELATED_SYSTEM` - System prompt for finding related content
   - `PROMPT_RELATED_USER` - User prompt for link suggestions

5. **Headline Translation**
   - `PROMPT_HEADLINE_SYSTEM` - System prompt for headlines
   - `PROMPT_HEADLINE_USER` - User prompt for headline translation

**Prompt Resolution Priority:**
1. Explicitly passed config (highest priority)
2. Active profile's custom prompt (from database)
3. Default hardcoded prompt (fallback)

### 4. UI Components

**Profile Manager (`ProfileManager.tsx`):**
- View all profiles
- Create new profiles with name, input/output directories, and description
- Edit existing profiles
- Delete profiles (except active one)
- Activate profiles (switches processing to that profile's directories and prompts)
- Visual indicator showing which profile is active

**Prompt Editor (`PromptEditor.tsx`):**
- Browse all LLM prompts organized by category
- View current prompt values (custom or default)
- Edit prompts with multi-line text editor
- Save custom prompts per profile
- Reset individual prompts to defaults
- Visual indicators showing which prompts are customized
- Expandable sections for better readability

**Integration in App:**
- New "Profile Management" section at bottom of main UI
- Shows active profile name and directories
- Collapsible sections to keep UI clean
- New "LLM Prompt Customization" section
- Both sections toggle on/off to reduce clutter

## How to Use

### Creating a New Profile

1. Scroll to the **Profile Management** section
2. Click **"Show Profiles"** to expand the section
3. Click **"+ New Profile"** button
4. Fill in the form:
   - **Name**: e.g., "Barcelona News" or "Retro Games"
   - **Input Directory**: e.g., "current/barcelona" (relative to project root)
   - **Output Directory**: e.g., "output/barcelona"
   - **Description**: Optional description of this profile
5. Click **"Create"**

### Switching Profiles

1. In the Profile Management section, find the profile you want to activate
2. Click the **"Activate"** button next to it
3. The UI will automatically:
   - Update the active profile indicator
   - Refresh the scan to use the new input directory
   - Apply that profile's custom prompts to all processing

### Customizing Prompts

1. Make sure you have a profile activated
2. Scroll to the **LLM Prompt Customization** section
3. Click **"Show Prompts"** to expand
4. Browse the prompt categories (Translation, Primary Source, Article Writing, etc.)
5. Click on a prompt name to expand and view its content
6. Click **"Edit"** to modify the prompt
7. Make your changes in the text area
8. Click **"Save"** to save the custom prompt
9. The prompt will now be used for all articles processed with this profile

**Resetting Prompts:**
- Custom prompts show a yellow **"CUSTOM"** badge
- Click **"Reset"** next to any custom prompt to revert to default

### Directory Structure

Profiles use relative paths from the project root:

```
project_root/
├── current/              (Default profile input)
│   ├── barcelona/        (Barcelona profile input)
│   └── retro-games/      (Retro Games profile input)
├── output/               (Default profile output)
│   ├── barcelona/        (Barcelona profile output)
│   └── retro-games/      (Retro Games profile output)
```

Directories are automatically created when you activate a profile.

### Example Workflow: Barcelona News Profile

1. **Create Profile:**
   - Name: "Barcelona News"
   - Input: "current/barcelona"
   - Output: "output/barcelona"
   - Description: "Barcelona-specific news articles from local sources"

2. **Customize Prompts:**
   - Edit `PROMPT_ARTICLE_SYSTEM` to emphasize Barcelona-specific context
   - Edit `PROMPT_TRANSLATION_USER` to prioritize Catalan language detection
   - Edit `PROMPT_PRIMARY_SYSTEM` to prefer `.cat` domains

3. **Use Profile:**
   - Place Barcelona article JSON files in `/current/barcelona/`
   - Click "Translate Headlines" (scans Barcelona directory)
   - Select articles and click "Start Run"
   - Articles processed with Barcelona-specific prompts
   - Output saved to `/output/barcelona/`

### Example Workflow: Retro Games Profile

1. **Create Profile:**
   - Name: "Retro Games"
   - Input: "current/retro-games"
   - Output: "output/retro-games"
   - Description: "Retro gaming news and reviews"

2. **Customize Prompts:**
   - Edit `PROMPT_ARTICLE_SYSTEM` to use gaming terminology and tone
   - Edit `PROMPT_PRIMARY_SYSTEM` to prefer gaming news sites
   - Edit `PROMPT_RELATED_USER` to focus on game franchises and platforms

3. **Use Profile:**
   - Place gaming articles in `/current/retro-games/`
   - Activate "Retro Games" profile
   - Process articles with gaming-focused prompts
   - Output saved to `/output/retro-games/`

## Technical Details

### Profile Storage

Profiles are stored in SQLite database at: `agent0_gui/agent0_gui.db`

**Profiles Table:**
```sql
CREATE TABLE profiles (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE,
    input_dir TEXT,
    output_dir TEXT,
    created_at TEXT,
    is_active INTEGER,
    description TEXT
)
```

**Profile Prompts Table:**
```sql
CREATE TABLE profile_prompts (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER,
    prompt_key TEXT,
    prompt_value TEXT,
    UNIQUE(profile_id, prompt_key)
)
```

### Prompt Resolution

The `resolve_prompt()` function in `prompts.py` checks three sources:

1. **Config Dict** (passed explicitly in code)
2. **Database** (active profile's custom prompts)
3. **Default** (hardcoded in module files)

This ensures backward compatibility while enabling full customization.

### API Integration

Scanner and pipeline automatically use active profile directories:

```python
from agent0_gui.profile_manager import get_profile_directories

# Get active profile's directories
dirs = get_profile_directories()
input_dir = dirs["input_dir"]   # Path object
output_dir = dirs["output_dir"]  # Path object
```

## Best Practices

### Profile Organization

1. **Use descriptive names**: "Barcelona News", "Tech Reviews", "Gaming Content"
2. **Organize by topic**: Keep related articles together
3. **One profile per content type**: Don't mix Barcelona news with gaming articles

### Prompt Customization

1. **Test incrementally**: Change one prompt at a time
2. **Document changes**: Use profile description to note customizations
3. **Keep backups**: Custom prompts are in database, back up periodically
4. **Reset if needed**: Can always reset individual prompts to defaults

### Directory Management

1. **Use relative paths**: "current/foo" not "/absolute/path/foo"
2. **Keep organized**: Separate input/output directories per profile
3. **Clean regularly**: Remove processed files from input directories

## Troubleshooting

### Profile not working

- **Check active profile**: Only one profile can be active at a time
- **Verify directories exist**: Directories are auto-created, but check permissions
- **Restart server**: If prompts not updating, restart with `--reload`

### Prompts not applying

- **Check profile is active**: Prompts only apply to active profile
- **Verify prompt keys**: Must match exact keys like `PROMPT_ARTICLE_SYSTEM`
- **Check database**: Custom prompts stored in `profile_prompts` table

### Scanner not finding files

- **Check input directory**: Should contain `.json` files
- **Verify path**: Relative to project root, not agent0_gui folder
- **Check file format**: Files must be valid JSON with required fields

## Advanced Usage

### Programmatic Profile Management

```python
from agent0_gui.profile_manager import (
    create_profile,
    set_active_profile,
    set_profile_prompt
)

# Create new profile
profile = create_profile(
    name="My Profile",
    input_dir="current/myprofile",
    output_dir="output/myprofile",
    description="Custom profile for testing"
)

# Activate it
set_active_profile(profile["id"])

# Set custom prompt
set_profile_prompt(
    profile["id"],
    "PROMPT_ARTICLE_SYSTEM",
    "You are a specialized writer for..."
)
```

### Backup and Restore

**Backup profiles:**
```bash
sqlite3 agent0_gui/agent0_gui.db ".backup profiles_backup.db"
```

**Export profiles:**
```bash
sqlite3 agent0_gui/agent0_gui.db "SELECT * FROM profiles;" > profiles.txt
sqlite3 agent0_gui/agent0_gui.db "SELECT * FROM profile_prompts;" > prompts.txt
```

## Future Enhancements

Potential improvements:

1. **Profile Templates**: Pre-configured profiles for common use cases
2. **Prompt Sharing**: Export/import custom prompts between profiles
3. **Profile Cloning**: Duplicate profile with all settings
4. **Batch Operations**: Apply prompts to multiple profiles at once
5. **Version Control**: Track prompt changes over time
6. **A/B Testing**: Compare output quality between different prompts

## Summary

The multi-profile system provides:

✅ **Isolation**: Different article types don't interfere with each other
✅ **Customization**: Full control over every LLM prompt
✅ **Organization**: Clean directory structure per content type
✅ **Flexibility**: Easy switching between profiles
✅ **Scalability**: Add unlimited profiles as needed

You can now process Barcelona news, retro games, tech reviews, or any other content type with optimized prompts and separate workflows!

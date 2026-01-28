# Upload and Scan Status Improvements

## Overview
Enhanced the file upload and directory scanning system with comprehensive status tracking, detailed error handling, and real-time progress feedback to resolve issues where users weren't getting feedback during uploads and scans.

## Problems Fixed

### 1. **Silent Upload Failures**
- **Issue**: Users uploading files for translation weren't getting any feedback from the app
- **Solution**: Added detailed logging throughout the upload process with clear status messages

### 2. **Scan Process Opacity**
- **Issue**: Directory scanning happened without any indication of progress
- **Solution**: Implemented progress callbacks and visual indicators showing scan status

### 3. **Poor Error Reporting**
- **Issue**: Errors were not clearly communicated to users
- **Solution**: Enhanced error messages with context and debugging hints

### 4. **Cloud Instance Compatibility**
- **Issue**: Local and cloud instances had different behaviors
- **Solution**: Ensured consistent logging and error handling across environments

## Changes Made

### Backend Changes (`agent0_scanner.py`)

#### Enhanced `scan_articles` Function
- Added `progress_callback` parameter for real-time status updates
- Emits progress events every 100 files (down from 1000 for better feedback)
- Reports scan start, progress, completion, and errors
- Provides detailed metrics: scanned count, found count, elapsed time

```python
def scan_articles(
    input_dir: str, 
    max_files: int = 10000, 
    timeout_seconds: int = 30, 
    recursive: bool = False,
    progress_callback: Optional[Callable[[dict], None]] = None
) -> list[Path]:
```

**Progress Events Emitted**:
- `status: "started"` - Scan begins
- `status: "progress"` - Every 100 files processed
- `status: "completed"` - Scan finishes successfully
- `status: "error"` - Directory doesn't exist or other errors

### Backend Changes (`agent0_gui/app.py`)

#### Enhanced `/api/upload` Endpoint
- Added comprehensive logging with `[UPLOAD]` prefix for easy tracking
- Detailed file-by-file processing logs
- Tracks saved, skipped, and error counts separately
- Returns detailed response including errors array
- Graceful error handling - doesn't fail entire upload if scan fails
- Better directory setup with fallback from symlink to copy

**New Response Format**:
```json
{
  "ok": true,
  "saved_count": 42,
  "skipped_count": 3,
  "root": "/path/to/workspace/current",
  "scanned_items": 42,
  "errors": ["error1", "error2"] // or null
}
```

#### Enhanced `/api/rescan` Endpoint
- Added comprehensive logging with `[RESCAN]` prefix
- Better error handling with try-catch blocks
- Logs mode, paths, and progress at each step
- Clears stale cache entries with count reporting
- Returns detailed error messages on failure

### Frontend Changes (`agent0_gui/web/src/pages/App.tsx`)

#### Enhanced `uploadFiles` Function
- Console logging at every step for debugging
- Sets multiple state variables for comprehensive status display
- Handles partial success (files uploaded but scan failed)
- Displays warnings from server response
- Better error message formatting

#### Enhanced `handleDirectoryPicker` Function
- Logs file collection process
- Validates files before upload
- Shows clear error if no valid files found
- Handles both modern and fallback file picker APIs
- Better error messages for user cancellation

#### Improved Status Display UI
- **Upload Status**: Blue animated spinner with "Uploading files..." message
- **Upload Success**: Green box with checkmark and file count
- **Upload Error**: Red box with detailed error and debugging hint
- **Scan Warning**: Amber box for non-critical issues
- **Scanning Status**: Blue animated spinner with "Scanning directory..." message
- **Translation Status**: Purple animated spinner with progress counter and elapsed time

## Status Messages Guide

### For Users
- **Blue boxes with spinner**: Operation in progress, please wait
- **Green boxes with ✓**: Operation completed successfully
- **Red boxes with ✗**: Critical error occurred, check details
- **Amber boxes with ⚠**: Warning, operation partially succeeded
- **Console logs**: Open browser console (F12) for detailed debugging information

### For Developers
All backend operations now log with prefixes:
- `[UPLOAD]` - File upload operations
- `[RESCAN]` - Directory scanning operations
- `[SCAN]` - Low-level file scanning (from agent0_scanner.py)
- `[PICKER]` - Frontend file picker operations (console)

## Testing Checklist

### Local Instance
- [ ] Upload directory with valid files
- [ ] Upload directory with no valid files
- [ ] Upload directory with mixed valid/invalid files
- [ ] Check console logs show detailed progress
- [ ] Verify error messages are clear and actionable

### Cloud Instance (Google Cloud)
- [ ] Upload files and verify workspace directory creation
- [ ] Check server logs for `[UPLOAD]` and `[RESCAN]` messages
- [ ] Verify symlink fallback to copy works
- [ ] Test with large directories (100+ files)
- [ ] Verify scan timeout handling

### Error Scenarios
- [ ] Upload non-article files only
- [ ] Upload to read-only filesystem (should show clear error)
- [ ] Network interruption during upload
- [ ] Scan directory that doesn't exist
- [ ] Scan directory with permission issues

## Debugging Guide

### User Reports "Not Getting Anything"

1. **Check Browser Console** (F12 → Console tab)
   - Look for `[UPLOAD]` and `[PICKER]` messages
   - Check for JavaScript errors
   - Verify network requests completed

2. **Check Server Logs**
   - Look for `[UPLOAD]`, `[RESCAN]`, and `[SCAN]` messages
   - Verify files were saved to disk
   - Check workspace directory permissions

3. **Verify File Types**
   - Only `.json`, `.md`, and `.markdown` files are processed
   - Check if files were filtered out

4. **Check Workspace Paths**
   - Local: `agent0_gui/workspace/current/`
   - Cloud: `/tmp/agent0_workspace/current/`

### Common Issues and Solutions

**Issue**: "No files uploaded"
- **Cause**: Only non-article files in directory
- **Solution**: Ensure directory contains .json, .md, or .markdown files

**Issue**: "Upload succeeded but no articles shown"
- **Cause**: Scan failed after upload
- **Solution**: Check server logs for scan errors, verify file permissions

**Issue**: "Symlink failed" in logs
- **Cause**: Filesystem doesn't support symlinks (Windows, some cloud environments)
- **Solution**: System automatically falls back to copy - this is normal

**Issue**: "Directory does not exist"
- **Cause**: Path is incorrect or permissions issue
- **Solution**: Verify path exists and is readable

## Performance Improvements

- Progress updates every 100 files (was 1000) for better feedback
- Scan timeout remains at 30 seconds for safety
- Max files limit remains at 10,000 for safety
- Upload processes files sequentially to avoid memory issues

## Future Enhancements (Not Implemented)

1. **Server-Sent Events for Upload Progress**
   - Real-time file-by-file upload progress
   - Would require streaming upload endpoint

2. **Progress Bar with Percentage**
   - Visual progress bar during scan
   - Would require more granular progress reporting

3. **Batch Upload Optimization**
   - Parallel file processing
   - Would need careful memory management

4. **Resumable Uploads**
   - Handle interrupted uploads
   - Would require upload session management

## Compatibility Notes

- Works with both local development and Google Cloud Run
- Handles read-only filesystems (Cloud Run)
- Falls back gracefully when symlinks aren't supported
- Compatible with all modern browsers
- Fallback for browsers without File System Access API

## Summary

These improvements provide comprehensive visibility into the upload and scanning process, making it clear to users what's happening at all times and providing detailed error messages when things go wrong. The extensive logging helps both users and developers quickly identify and resolve issues.

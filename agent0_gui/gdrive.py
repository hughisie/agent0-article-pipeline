import os
from typing import Optional, List, Dict
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "17txivAocXR4R5qMsWi4vYUB6Kg2K1N1m")


class DriveError(Exception):
    pass


def get_drive_service(access_token: str):
    """Create Google Drive service from access token"""
    credentials = Credentials(token=access_token)
    return build('drive', 'v3', credentials=credentials)


def list_files_in_folder(
    access_token: str, 
    folder_id: Optional[str] = None,
    page_size: int = 100,
    page_token: Optional[str] = None,
    file_types: Optional[List[str]] = None
) -> Dict:
    """
    List files in a Google Drive folder
    
    Args:
        access_token: Google OAuth access token
        folder_id: Folder ID to list files from (defaults to configured folder)
        page_size: Number of files per page
        page_token: Token for pagination
        file_types: List of MIME types to filter (e.g., ['application/json', 'text/markdown'])
    
    Returns:
        Dictionary with 'files' list and 'nextPageToken' if more results available
    """
    try:
        service = get_drive_service(access_token)
        
        # Use configured folder if not specified
        if not folder_id:
            folder_id = GOOGLE_DRIVE_FOLDER_ID
        
        # Build query
        query = f"'{folder_id}' in parents and trashed=false"
        
        # Add file type filter if specified
        if file_types:
            mime_conditions = " or ".join([f"mimeType='{mt}'" for mt in file_types])
            query += f" and ({mime_conditions})"
        
        # Call Drive API
        results = service.files().list(
            q=query,
            pageSize=page_size,
            pageToken=page_token,
            fields="nextPageToken, files(id, name, mimeType, size, modifiedTime, webViewLink, thumbnailLink, createdTime)",
            orderBy="modifiedTime desc"
        ).execute()
        
        files = results.get('files', [])
        next_page_token = results.get('nextPageToken')
        
        return {
            'files': files,
            'nextPageToken': next_page_token,
            'folderName': get_folder_name(access_token, folder_id)
        }
        
    except HttpError as error:
        raise DriveError(f"Failed to list files: {error}")


def get_folder_name(access_token: str, folder_id: str) -> str:
    """Get folder name from folder ID"""
    try:
        service = get_drive_service(access_token)
        folder = service.files().get(
            fileId=folder_id,
            fields="name"
        ).execute()
        return folder.get('name', 'Unknown Folder')
    except HttpError:
        return 'Unknown Folder'


def download_file_content(access_token: str, file_id: str) -> bytes:
    """Download file content from Google Drive"""
    try:
        service = get_drive_service(access_token)
        
        # Get file metadata first to check MIME type
        file_metadata = service.files().get(
            fileId=file_id,
            fields="mimeType, name"
        ).execute()
        
        # Download file content
        request = service.files().get_media(fileId=file_id)
        content = request.execute()
        
        return content
        
    except HttpError as error:
        raise DriveError(f"Failed to download file: {error}")


def get_file_metadata(access_token: str, file_id: str) -> Dict:
    """Get file metadata from Google Drive"""
    try:
        service = get_drive_service(access_token)
        
        file = service.files().get(
            fileId=file_id,
            fields="id, name, mimeType, size, modifiedTime, webViewLink, thumbnailLink, createdTime, parents"
        ).execute()
        
        return file
        
    except HttpError as error:
        raise DriveError(f"Failed to get file metadata: {error}")


def search_files(
    access_token: str,
    query: str,
    folder_id: Optional[str] = None,
    page_size: int = 50
) -> List[Dict]:
    """
    Search files in Google Drive
    
    Args:
        access_token: Google OAuth access token
        query: Search query (file name or content)
        folder_id: Optional folder ID to restrict search
        page_size: Number of results
    
    Returns:
        List of file metadata dictionaries
    """
    try:
        service = get_drive_service(access_token)
        
        # Build search query
        search_query = f"name contains '{query}' and trashed=false"
        
        if folder_id:
            search_query = f"'{folder_id}' in parents and " + search_query
        
        results = service.files().list(
            q=search_query,
            pageSize=page_size,
            fields="files(id, name, mimeType, size, modifiedTime, webViewLink)",
            orderBy="modifiedTime desc"
        ).execute()
        
        return results.get('files', [])
        
    except HttpError as error:
        raise DriveError(f"Failed to search files: {error}")


def get_folder_breadcrumbs(access_token: str, folder_id: str) -> List[Dict]:
    """Get breadcrumb trail for a folder"""
    try:
        service = get_drive_service(access_token)
        breadcrumbs = []
        current_id = folder_id
        
        while current_id:
            folder = service.files().get(
                fileId=current_id,
                fields="id, name, parents"
            ).execute()
            
            breadcrumbs.insert(0, {
                'id': folder['id'],
                'name': folder['name']
            })
            
            # Move to parent
            parents = folder.get('parents', [])
            current_id = parents[0] if parents else None
            
            # Prevent infinite loops
            if len(breadcrumbs) > 10:
                break
        
        return breadcrumbs
        
    except HttpError as error:
        raise DriveError(f"Failed to get breadcrumbs: {error}")

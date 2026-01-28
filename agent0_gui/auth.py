import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from google.oauth2 import id_token
from google.auth.transport import requests
import jwt
from itsdangerous import URLSafeTimedSerializer

# Configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
JWT_SECRET = os.getenv("JWT_SECRET", "change-this-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

security = HTTPBearer(auto_error=False)


class AuthError(Exception):
    pass


def verify_google_token(token: str) -> dict:
    """Verify Google OAuth token and return user info"""
    if not GOOGLE_CLIENT_ID:
        raise AuthError("GOOGLE_CLIENT_ID not configured")
    
    try:
        idinfo = id_token.verify_oauth2_token(
            token, 
            requests.Request(), 
            GOOGLE_CLIENT_ID
        )
        
        if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            raise AuthError("Wrong issuer")
        
        return {
            "email": idinfo["email"],
            "name": idinfo.get("name"),
            "picture": idinfo.get("picture"),
            "sub": idinfo["sub"]
        }
    except ValueError as e:
        raise AuthError(f"Invalid token: {str(e)}")


def create_access_token(user_info: dict) -> str:
    """Create JWT access token for authenticated user"""
    expires = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    payload = {
        "sub": user_info["sub"],
        "email": user_info["email"],
        "name": user_info.get("name"),
        "exp": expires
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict:
    """Verify JWT token and return user info"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthError("Token has expired")
    except jwt.InvalidTokenError:
        raise AuthError("Invalid token")


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[dict]:
    """Get current user from JWT token (optional authentication)"""
    # If running locally without auth enabled, skip authentication
    if not GOOGLE_CLIENT_ID:
        return None
    
    if not credentials:
        return None
    
    try:
        user = verify_token(credentials.credentials)
        return user
    except AuthError:
        return None


async def require_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> dict:
    """Require authentication - raises 401 if not authenticated"""
    # If running locally without auth enabled, return dummy user
    if not GOOGLE_CLIENT_ID:
        return {"email": "local@dev", "name": "Local Dev", "sub": "local"}
    
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        user = verify_token(credentials.credentials)
        return user
    except AuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


def create_state_token() -> str:
    """Create state token for OAuth flow (CSRF protection)"""
    serializer = URLSafeTimedSerializer(JWT_SECRET)
    return serializer.dumps({"oauth": "google"})


def verify_state_token(token: str, max_age: int = 600) -> bool:
    """Verify state token (max_age in seconds, default 10 minutes)"""
    try:
        serializer = URLSafeTimedSerializer(JWT_SECRET)
        serializer.loads(token, max_age=max_age)
        return True
    except Exception:
        return False

"""
FastAPI dependencies for v1 API.

Provides dependency injection for database connections, authentication,
rate limiting, and other shared functionality across endpoints.
"""

from typing import Optional
from fastapi import Depends, HTTPException, Header, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ...database.schema import DatabaseManager
from ..auth import authenticate_api_key, AuthResponse

# Security scheme for API key authentication
security = HTTPBearer(auto_error=False)


class DatabaseDependency:
    """Database dependency provider."""

    def __init__(self, db_manager: DatabaseManager):
        """Initialize with database manager instance."""
        self.db_manager = db_manager

    @property
    def dependency(self):
        """Return the dependency function."""
        def get_database():
            return self.db_manager
        return Depends(get_database)


async def get_api_key(
    authorization: Optional[HTTPAuthorizationCredentials] = Depends(security),
    api_key: Optional[str] = Query(None, description="API key for authentication"),
    x_api_key: Optional[str] = Header(None, description="API key via header")
) -> str:
    """
    Extract API key from various sources (Bearer token, query param, or header).

    Args:
        authorization: Bearer token from Authorization header
        api_key: API key from query parameter
        x_api_key: API key from X-API-Key header

    Returns:
        The API key string

    Raises:
        HTTPException: If no API key is provided
    """
    # Try to get API key from different sources
    if authorization and authorization.credentials:
        return authorization.credentials
    elif api_key:
        return api_key
    elif x_api_key:
        return x_api_key
    else:
        raise HTTPException(
            status_code=401,
            detail="API key required. Provide via Authorization header, api_key query param, or X-API-Key header"
        )


async def get_authenticated_user(api_key: str = Depends(get_api_key)) -> AuthResponse:
    """
    Authenticate user and return authentication details.

    Args:
        api_key: API key from get_api_key dependency

    Returns:
        AuthResponse with authentication details

    Raises:
        HTTPException: If authentication fails
    """
    auth_response = authenticate_api_key(api_key)

    if not auth_response.authenticated:
        raise HTTPException(
            status_code=401,
            detail=auth_response.message or "Authentication failed"
        )

    return auth_response


async def require_permission(
    required_permission: str,
    auth: AuthResponse = Depends(get_authenticated_user)
) -> AuthResponse:
    """
    Check if authenticated user has required permission.

    Args:
        required_permission: Permission string required
        auth: Authentication response from get_authenticated_user

    Returns:
        AuthResponse if user has permission

    Raises:
        HTTPException: If user lacks required permission
    """
    if required_permission not in auth.permissions:
        raise HTTPException(
            status_code=403,
            detail=f"Permission '{required_permission}' required"
        )

    return auth


# Common permission dependencies
async def require_read_permission(auth: AuthResponse = Depends(get_authenticated_user)) -> AuthResponse:
    """Require read permission."""
    return await require_permission("read", auth)


async def require_write_permission(auth: AuthResponse = Depends(get_authenticated_user)) -> AuthResponse:
    """Require write permission."""
    return await require_permission("write", auth)


async def require_admin_permission(auth: AuthResponse = Depends(get_authenticated_user)) -> AuthResponse:
    """Require admin permission."""
    return await require_permission("admin", auth)


# Optional dependencies for endpoints that support both authenticated and unauthenticated access
async def get_optional_authenticated_user(
    api_key: Optional[str] = Depends(get_api_key)
) -> Optional[AuthResponse]:
    """
    Optionally authenticate user if API key is provided.

    Args:
        api_key: Optional API key

    Returns:
        AuthResponse if authenticated, None otherwise
    """
    if not api_key:
        return None

    try:
        return await get_authenticated_user(api_key)
    except HTTPException:
        return None


def create_pagination_dependency(max_limit: int = 100):
    """
    Create a pagination dependency with configurable max limit.

    Args:
        max_limit: Maximum allowed limit value

    Returns:
        Dependency function for pagination parameters
    """
    def get_pagination_params(
        limit: int = Query(20, ge=1, le=max_limit, description="Number of items per page"),
        offset: int = Query(0, ge=0, description="Offset for pagination")
    ) -> dict:
        return {"limit": limit, "offset": offset}

    return Depends(get_pagination_params)


def create_date_range_dependency(max_days: int = 365):
    """
    Create a date range dependency with configurable max range.

    Args:
        max_days: Maximum allowed days in range

    Returns:
        Dependency function for date range parameters
    """
    def get_date_range_params(
        days: int = Query(30, ge=1, le=max_days, description="Number of days"),
        start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
        end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)")
    ) -> dict:
        return {
            "days": days,
            "start_date": start_date,
            "end_date": end_date
        }

    return Depends(get_date_range_params)
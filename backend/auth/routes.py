"""Authentication and user-management API routes.

These endpoints issue JWTs, refresh sessions, change passwords, and let higher
roles manage lower roles according to backend.auth.roles. The route handlers use
the in-memory user cache from auth.py, which is persisted back to SQLite.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from .auth import *
from .roles import can_manage


router = APIRouter()
security = HTTPBearer()


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """FastAPI dependency that validates bearer access tokens."""
    token = credentials.credentials
    payload = decode_token(token)

    if not payload or payload.get("token_type", ACCESS_TOKEN_TYPE) != ACCESS_TOKEN_TYPE:
        raise HTTPException(status_code=401, detail="Invalid token")

    return payload


def build_token_response(username: str, role: str):
    """Return the access/refresh token payload expected by the frontend."""
    payload = {
        "sub": username,
        "role": role,
    }
    return {
        "access_token": create_access_token(payload),
        "refresh_token": create_refresh_token(payload),
        "token_type": "bearer",
        "username": username,
        "role": role,
    }


class SignupUser(BaseModel):
    """Request body for creating a managed user account."""

    username: str
    password: str
    role: str = "viewer"


class LoginUser(BaseModel):
    """Request body for username/password login."""

    username: str
    password: str


class RefreshTokenRequest(BaseModel):
    """Request body for replacing an expired access token."""

    refresh_token: str


class TokenResponse(BaseModel):
    """Response body shared by login and refresh-token endpoints."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    username: str
    role: str


class ChangePasswordRequest(BaseModel):
    """Request body for changing the current user's password."""

    current_password: str
    new_password: str


@router.post("/login", response_model=TokenResponse)
def login(user: LoginUser):
    """Validate credentials and return access plus refresh tokens."""
    db_user = fake_users_db.get(user.username)

    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(user.password, db_user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return build_token_response(user.username, db_user["role"])


@router.post("/refresh-token", response_model=TokenResponse)
def refresh_token(req: RefreshTokenRequest):
    """Use a valid refresh token to issue a fresh access token."""
    payload = decode_token(req.refresh_token)

    if not payload or payload.get("token_type") != REFRESH_TOKEN_TYPE:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    username = payload.get("sub")
    db_user = fake_users_db.get(username)
    if not username or not db_user:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    return build_token_response(username, db_user["role"])


@router.post("/change-password")
def change_password(req: ChangePasswordRequest, user=Depends(get_current_user)):
    """Change the current user's password after verifying the old password."""
    username = user["sub"]
    db_user = fake_users_db.get(username)

    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(req.current_password, db_user["password"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    new_password = req.new_password.strip()
    if len(new_password) < 4:
        raise HTTPException(status_code=400, detail="New password must be at least 4 characters")

    if verify_password(new_password, db_user["password"]):
        raise HTTPException(status_code=400, detail="Enter a different password from your current password")

    fake_users_db[username]["password"] = hash_password(new_password)
    save_users()

    return {"message": "Password changed successfully"}


# User-management endpoints are intentionally limited to admin/manager roles,
# and can_manage() prevents managers from creating or deleting peers/admins.
ALLOWED_USER_ROLES = {"manager", "analyst", "viewer", "guest"}
USER_MANAGEMENT_ROLES = {"admin", "manager"}


def public_users_for(role):
    """Return visible users for an admin/manager without exposing hashes."""
    return {
        username: {
            "username": data["username"],
            "role": data["role"],
        }
        for username, data in fake_users_db.items()
        if role == "admin" or can_manage(role, data["role"])
    }


@router.post("/create-user")
def create_user(new_user: SignupUser, user=Depends(get_current_user)):
    """Create a lower-role user account."""
    current_role = user["role"]

    if current_role not in USER_MANAGEMENT_ROLES:
        raise HTTPException(status_code=403, detail="Only admin or manager can create users")

    if new_user.role not in ALLOWED_USER_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Role must be one of: {', '.join(sorted(ALLOWED_USER_ROLES))}",
        )

    if not can_manage(current_role, new_user.role):
        raise HTTPException(status_code=403, detail=f"{current_role} cannot create {new_user.role} users")

    new_username = new_user.username.strip()
    if not new_username:
        raise HTTPException(status_code=400, detail="Username required")

    if not new_user.password:
        raise HTTPException(status_code=400, detail="Password required")

    if new_username in fake_users_db:
        raise HTTPException(status_code=400, detail="User exists")

    fake_users_db[new_username] = {
        "username": new_username,
        "password": hash_password(new_user.password),
        "role": new_user.role,
    }

    save_users()

    return {"message": f"{new_user.role} created successfully"}


@router.delete("/delete-user/{username}")
def delete_user(username: str, user=Depends(get_current_user)):
    """Delete a lower-role user account."""
    current_role = user["role"]
    current_username = user["sub"]

    if current_role not in USER_MANAGEMENT_ROLES:
        raise HTTPException(status_code=403, detail="Only admin or manager can delete users")

    if username == current_username:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")

    target = fake_users_db.get(username)

    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if not can_manage(current_role, target["role"]):
        raise HTTPException(status_code=403, detail=f"{current_role} cannot delete {target['role']} users")

    del fake_users_db[username]
    save_users()

    return {"message": "User deleted successfully"}


@router.get("/users")
def list_users(user=Depends(get_current_user)):
    """List manageable users for the current admin/manager."""
    role = user["role"]

    if role not in USER_MANAGEMENT_ROLES:
        raise HTTPException(status_code=403, detail="Only admin or manager can list users")

    return {"users": public_users_for(role)}

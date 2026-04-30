from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from .auth import *
from .roles import can_manage


router = APIRouter()
security = HTTPBearer()


# -------------------------------
# AUTH DEPENDENCY (JWT PROTECTION)
# -------------------------------
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    payload = decode_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    return payload


# -------------------------------
# SCHEMAS
# -------------------------------
class SignupUser(BaseModel):
    username: str
    password: str
    role: str = "viewer"


class LoginUser(BaseModel):
    username: str
    password: str


# -------------------------------
# LOGIN
# -------------------------------
@router.post("/login")
def login(user: LoginUser):

    db_user = fake_users_db.get(user.username)

    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(user.password, db_user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token({
        "sub": user.username,
        "role": db_user["role"]
    })

    return {
        "access_token": token,
        "role": db_user["role"]
    }


# -------------------------------
# 🔔 NOTIFICATIONS
# -------------------------------
# -------------------------------
# USER MANAGEMENT
# -------------------------------
ALLOWED_USER_ROLES = {"manager", "analyst", "viewer", "guest"}
USER_MANAGEMENT_ROLES = {"admin", "manager"}


def public_users_for(role):
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


# -------------------------------
# ❌ DELETE USER
# -------------------------------
@router.delete("/delete-user/{username}")
def delete_user(username: str, user=Depends(get_current_user)):

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


# -------------------------------
# 📋 LIST USERS
# -------------------------------
@router.get("/users")
def list_users(user=Depends(get_current_user)):

    role = user["role"]

    if role not in USER_MANAGEMENT_ROLES:
        raise HTTPException(status_code=403, detail="Only admin or manager can list users")

    return {"users": public_users_for(role)}


# -------------------------------
# 📂 FILE HISTORY
# -------------------------------

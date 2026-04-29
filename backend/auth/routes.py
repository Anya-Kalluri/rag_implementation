from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from .auth import *


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
# 👑 CREATE USER (Admin only)
# -------------------------------
ALLOWED_USER_ROLES = {"manager", "analyst", "viewer", "guest"}

@router.post("/create-user")
def create_user(new_user: SignupUser, user=Depends(get_current_user)):

    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admin can create users")

    if new_user.role not in ALLOWED_USER_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Role must be one of: {', '.join(sorted(ALLOWED_USER_ROLES))}",
        )

    if new_user.username in fake_users_db:
        raise HTTPException(status_code=400, detail="User exists")

    fake_users_db[new_user.username] = {
        "username": new_user.username,
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

    if current_role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can delete users")

    target = fake_users_db.get(username)

    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    del fake_users_db[username]
    save_users()

    return {"message": "User deleted successfully"}


# -------------------------------
# 📋 LIST USERS
# -------------------------------
@router.get("/users")
def list_users(user=Depends(get_current_user)):

    role = user["role"]

    if role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can list users")

    return {"users": fake_users_db}


# -------------------------------
# 📂 FILE HISTORY
# -------------------------------

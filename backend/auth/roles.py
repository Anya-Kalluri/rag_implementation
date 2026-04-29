from fastapi import HTTPException

ROLE_HIERARCHY = {
    "admin": 4,
    "manager": 3,
    "analyst": 2,
    "viewer": 1,
    "guest": 0,
}


def can_manage(current_role, target_role):
    return ROLE_HIERARCHY.get(current_role, -1) > ROLE_HIERARCHY.get(target_role, -1)


def require_role(user_role, allowed_roles):
    if user_role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Permission denied")

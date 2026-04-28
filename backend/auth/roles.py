from fastapi import HTTPException

ROLE_HIERARCHY = {
    "admin": 5,
    "manager": 4,
    "analyst": 3,
    "viewer": 2,
    "guest": 1
}


def can_manage(current_role, target_role):
    if current_role == "admin":
        return True

    if current_role == "manager":
        return ROLE_HIERARCHY[target_role] < ROLE_HIERARCHY["manager"]

    return False


def require_role(user_role, allowed_roles):
    if user_role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Permission denied")
ROLE_HIERARCHY = {
    "admin": 4,
    "manager": 3,
    "analyst": 2,
    "viewer": 1,
    "guest": 0
}

def can_manage(current_role, target_role):
    return ROLE_HIERARCHY[current_role] > ROLE_HIERARCHY[target_role]
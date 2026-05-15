"""Role hierarchy helpers for authorization checks."""

from fastapi import HTTPException


# Higher numbers can manage lower numbers. Equal roles cannot manage each other,
# which prevents managers from editing other managers or admins.
ROLE_HIERARCHY = {
    "admin": 4,
    "manager": 3,
    "analyst": 2,
    "viewer": 1,
    "guest": 0,
}


def can_manage(current_role, target_role):
    """Return True when current_role is strictly above target_role."""
    return ROLE_HIERARCHY.get(current_role, -1) > ROLE_HIERARCHY.get(target_role, -1)


def require_role(user_role, allowed_roles):
    """Raise a FastAPI 403 when a role is not allowed for an action."""
    if user_role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Permission denied")

"""Role authentication. Passwords only come from environment; public reads stay anonymous."""

import os
import secrets
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

Role = Literal["editor", "manager", "expert"]
security = HTTPBasic()
router = APIRouter()


class Identity(BaseModel):
    role: Role


def identity(credentials: Annotated[HTTPBasicCredentials, Depends(security)]) -> Identity:
    expected = os.environ.get(f"{credentials.username.upper()}_PASSWORD", "")
    accepted = credentials.username in ("editor", "manager", "expert")
    same = secrets.compare_digest(credentials.password.encode(), expected.encode())
    if not accepted or not expected or not same:
        raise HTTPException(401, "Неверный логин или пароль", headers={"WWW-Authenticate": "Basic"})
    return Identity(role=credentials.username)


def editor(user: Annotated[Identity, Depends(identity)]) -> Identity:
    if user.role != "editor":
        raise HTTPException(403, "Нужна роль редактора")
    return user


def manager(user: Annotated[Identity, Depends(identity)]) -> Identity:
    if user.role != "manager":
        raise HTTPException(403, "Нужна роль менеджера")
    return user


def reader(user: Annotated[Identity, Depends(identity)]) -> Identity:
    """Read-only staff view: the manager and the expert. Writes use `manager` (#132)."""
    if user.role not in ("manager", "expert"):
        raise HTTPException(403, "Нужна роль менеджера или эксперта")
    return user


@router.get("/api/auth/me")
def me(user: Annotated[Identity, Depends(identity)]) -> Identity:
    return user

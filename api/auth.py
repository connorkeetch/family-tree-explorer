"""Accounts + session auth.

Invite-gated email/password registration (set INVITE_CODE to require it), PBKDF2
password hashing (stdlib — no heavy deps), and a signed HTTP-only session cookie
(Starlette SessionMiddleware). `current_user` is the dependency every protected
route uses. Structured so a "Sign in with FamilySearch" OAuth provider (Phase 4)
slots in alongside this one.
"""
import hashlib
import hmac
import os
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .db import get_db
from .models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])

_PBKDF2_ITERS = 200_000


def _derive(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), _PBKDF2_ITERS
    ).hex()


def hash_password(password: str) -> tuple[str, str]:
    salt = secrets.token_hex(16)
    return _derive(password, salt), salt


def verify_password(password: str, pw_hash: str, salt: str) -> bool:
    return hmac.compare_digest(_derive(password, salt), pw_hash)


class Credentials(BaseModel):
    email: str
    password: str
    invite: str | None = None


class UserOut(BaseModel):
    id: int
    email: str


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    uid = request.session.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="not authenticated")
    user = db.get(User, uid)
    if user is None:
        request.session.clear()
        raise HTTPException(status_code=401, detail="not authenticated")
    return user


@router.post("/register", response_model=UserOut)
def register(creds: Credentials, request: Request, db: Session = Depends(get_db)):
    required = os.environ.get("INVITE_CODE")
    if required and creds.invite != required:
        raise HTTPException(status_code=403, detail="a valid invite code is required")
    email = creds.email.strip().lower()
    if not email or not creds.password:
        raise HTTPException(status_code=400, detail="email and password are required")
    if len(creds.password) < 8:
        raise HTTPException(status_code=400, detail="password must be at least 8 characters")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="that email is already registered")
    pw_hash, salt = hash_password(creds.password)
    user = User(email=email, pw_hash=pw_hash, pw_salt=salt)
    db.add(user)
    db.commit()
    db.refresh(user)
    request.session["uid"] = user.id
    return UserOut(id=user.id, email=user.email)


@router.post("/login", response_model=UserOut)
def login(creds: Credentials, request: Request, db: Session = Depends(get_db)):
    email = creds.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if user is None or not verify_password(creds.password, user.pw_hash, user.pw_salt):
        raise HTTPException(status_code=401, detail="invalid email or password")
    request.session["uid"] = user.id
    return UserOut(id=user.id, email=user.email)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return UserOut(id=user.id, email=user.email)

from passlib.context import CryptContext
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from webapp.database import get_db, User
import secrets
import os

# Try to load from .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Use environment variable or a fixed key for development
# IMPORTANT: Always set JWT_SECRET_KEY in production!
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    print("WARNING: Using default JWT secret key. Set JWT_SECRET_KEY environment variable!")
    SECRET_KEY = "development-secret-key-do-not-use-in-production"

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()

def create_user(db: Session, email: str, password: str):
    hashed_password = get_password_hash(password)
    calendar_token = secrets.token_urlsafe(32)
    db_user = User(email=email, hashed_password=hashed_password, calendar_token=calendar_token)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def authenticate_user(db: Session, email: str, password: str):
    user = get_user_by_email(db, email)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user

async def get_current_user(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    if not token:
        print("No access_token cookie found")
        return None
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            print("No email in token payload")
            return None
    except JWTError as e:
        print(f"JWT decode error: {e}")
        return None
    
    user = get_user_by_email(db, email=email)
    if user is None:
        print(f"No user found for email: {email}")
        return None
    return user

async def get_current_user_required(request: Request, db: Session = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
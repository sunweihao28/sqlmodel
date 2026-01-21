from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
import database, models, schemas, auth

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/register", response_model=schemas.Token)
def register(user: schemas.UserCreate, db: Session = Depends(database.get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = auth.get_password_hash(user.password)
    new_user = models.User(
        email=user.email,
        hashed_password=hashed_password,
        full_name=user.full_name
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    access_token = auth.create_access_token(
        data={"sub": new_user.email},
        expires_delta=timedelta(hours=24)
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_name": new_user.full_name,
        "user_email": new_user.email
    }

@router.post("/token", response_model=schemas.Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = auth.create_access_token(
        data={"sub": user.email},
        expires_delta=timedelta(hours=24)
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_name": user.full_name,
        "user_email": user.email
    }

@router.get("/me")
def get_current_user_info(current_user: models.User = Depends(auth.get_current_user)):
    """获取当前用户信息，用于验证token有效性"""
    return {
        "id": current_user.email,
        "name": current_user.full_name,
        "email": current_user.email
    }
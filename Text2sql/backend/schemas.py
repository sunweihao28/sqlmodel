from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

# --- User Schemas ---
class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str
    full_name: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(UserBase):
    id: int
    full_name: str
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str
    user_name: str
    user_email: str

# --- File Schemas ---
class FileResponse(BaseModel):
    id: int
    filename: str
    file_type: str
    upload_time: datetime
    
    class Config:
        from_attributes = True
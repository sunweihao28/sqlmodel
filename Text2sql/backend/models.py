from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    full_name = Column(String)
    hashed_password = Column(String)
    # 存储用户的 API Key 配置，JSON 字符串格式
    api_config = Column(Text, nullable=True) 

    files = relationship("UploadedFile", back_populates="owner")

class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String)      # 原始文件名 (e.g., data.csv)
    file_path = Column(String)     # 服务器上存储的路径 (e.g., storage/uuid.db)
    file_type = Column(String)     # sqlite, csv, excel
    upload_time = Column(DateTime, default=datetime.utcnow)
    
    user_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="files")
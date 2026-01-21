from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
import database, models, schemas, auth
from utils.file_processor import process_uploaded_file
import os

router = APIRouter(prefix="/api/files", tags=["files"])

@router.post("/upload", response_model=schemas.FileResponse)
async def upload_file(
    file: UploadFile = File(...),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db)
):
    try:
        # 1. 处理文件 (转为 SQLite)
        saved_path = process_uploaded_file(file, file.filename)
        
        # 2. 记录到数据库
        new_file = models.UploadedFile(
            filename=file.filename,
            file_path=saved_path,
            file_type="sqlite", # 处理后统一都是 sqlite
            user_id=current_user.id
        )
        db.add(new_file)
        db.commit()
        db.refresh(new_file)
        
        return new_file
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
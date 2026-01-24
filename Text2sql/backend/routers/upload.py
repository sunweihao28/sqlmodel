from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
import shutil
import os
import database, models, auth

router = APIRouter(prefix="/api/files", tags=["files"])
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/upload")
def upload_file(
    file: UploadFile = File(...),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db)
):
    # [修改] 步骤1: 检查数据库中是否已存在该用户上传的同名文件
    existing_file = db.query(models.UploadedFile).filter(
        models.UploadedFile.user_id == current_user.id,
        models.UploadedFile.filename == file.filename
    ).first()

    # 使用 user_id 前缀防止不同用户文件名冲突
    file_path = f"{UPLOAD_DIR}/{current_user.id}_{file.filename}"
    
    # 物理保存文件 (即使数据库有记录，覆盖物理文件也是安全的，或者您可以选择跳过)
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # [修改] 步骤2: 如果数据库已有记录，直接返回旧的 ID，不要 insert 新行
    if existing_file:
        # 更新一下文件路径（以防万一）
        existing_file.file_path = file_path 
        db.commit()
        db.refresh(existing_file)
        
        return {
            "id": existing_file.id, 
            "filename": existing_file.filename, 
            "file_path": existing_file.file_path, 
            "status": "updated",
            "message": "File already exists, updated content."
        }
    else:
        # [修改] 步骤3: 只有不存在时，才创建新记录
        new_file = models.UploadedFile(
            user_id=current_user.id,
            filename=file.filename,
            file_path=file_path
        )
        db.add(new_file)
        db.commit()
        db.refresh(new_file)
        return {
            "id": new_file.id, 
            "filename": new_file.filename, 
            "file_path": new_file.file_path, 
            "status": "created"
        }
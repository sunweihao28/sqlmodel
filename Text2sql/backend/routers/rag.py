
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form
from sqlalchemy.orm import Session
import shutil
import os
import tempfile
import database, models, auth
from services.rag_service import rag_service_instance
from typing import Optional

router = APIRouter(prefix="/api/rag", tags=["rag"])

@router.get("/documents")
def list_documents(current_user: models.User = Depends(auth.get_current_user)):
    """列出当前用户的所有文档"""
    return rag_service_instance.list_documents(current_user.id)

@router.post("/upload")
def upload_document(
    file: UploadFile = File(...),
    api_key: Optional[str] = Form(None),
    base_url: Optional[str] = Form(None),
    current_user: models.User = Depends(auth.get_current_user)
):
    """上传并索引文档 (User isolated)"""
    # 保存到临时文件
    suffix = os.path.splitext(file.filename)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    
    try:
        doc_id = rag_service_instance.add_document(
            current_user.id,
            tmp_path, 
            file.filename,
            api_key=api_key,
            base_url=base_url
        )
        return {"id": doc_id, "filename": file.filename, "status": "indexed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

@router.delete("/documents/{doc_id}")
def delete_document(
    doc_id: str,
    api_key: Optional[str] = None, 
    current_user: models.User = Depends(auth.get_current_user)
):
    """删除文档 (User isolated)"""
    success = rag_service_instance.remove_document(current_user.id, doc_id, api_key=api_key)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found or failed to delete")
    return {"status": "deleted"}

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, text
import models, database, auth
import traceback

router = APIRouter(prefix="/api/db", tags=["database"])

class ConnectionTestRequest(BaseModel):
    type: str # mysql, postgres
    host: str
    port: str
    database: str
    user: str
    password: str

@router.post("/connect")
def connect_database(
    req: ConnectionTestRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db)
):
    """Test connection and save if successful"""
    
    # 1. Build URL
    url = ""
    try:
        if req.type == 'mysql':
            url = f"mysql+pymysql://{req.user}:{req.password}@{req.host}:{req.port}/{req.database}"
        elif req.type == 'postgres':
            url = f"postgresql+psycopg2://{req.user}:{req.password}@{req.host}:{req.port}/{req.database}"
        else:
            raise HTTPException(status_code=400, detail="Unsupported database type")
            
        # 2. Test Connection
        print(f"Testing connection to: {req.type}://{req.host}:{req.port}/{req.database} user={req.user}")
        engine = create_engine(url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("Connection successful")
            
    except Exception as e:
        print(f"Connection Failed: {str(e)}")
        # traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"Connection failed: {str(e)}")

    # 3. Save to DB
    # Check if exists to update
    existing = db.query(models.DatabaseConnection).filter(
        models.DatabaseConnection.user_id == current_user.id,
        models.DatabaseConnection.host == req.host,
        models.DatabaseConnection.database_name == req.database
    ).first()

    if existing:
        existing.db_type = req.type
        existing.port = req.port
        existing.username = req.user
        existing.password = req.password
        db.commit()
        db.refresh(existing)
        return {"id": existing.id, "message": "Connection updated"}
    
    new_conn = models.DatabaseConnection(
        user_id=current_user.id,
        name=f"{req.host}/{req.database}",
        db_type=req.type,
        host=req.host,
        port=req.port,
        database_name=req.database,
        username=req.user,
        password=req.password
    )
    db.add(new_conn)
    db.commit()
    db.refresh(new_conn)
    
    return {"id": new_conn.id, "message": "Connection successful"}
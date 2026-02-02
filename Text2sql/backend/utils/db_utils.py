import pandas as pd
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import Session
import models
import os

def get_engine_for_source(db: Session, file_id: int = None, connection_id: int = None, user_id: int = None):
    """
    Factory to create SQLAlchemy engine based on file_id (SQLite) or connection_id (MySQL/PG)
    """
    if file_id:
        file_record = db.query(models.UploadedFile).filter(
            models.UploadedFile.id == file_id,
            models.UploadedFile.user_id == user_id
        ).first()
        if not file_record or not os.path.exists(file_record.file_path):
            raise ValueError("Database file not found")
        return create_engine(f"sqlite:///{file_record.file_path}")
    
    if connection_id:
        conn_record = db.query(models.DatabaseConnection).filter(
            models.DatabaseConnection.id == connection_id,
            models.DatabaseConnection.user_id == user_id
        ).first()
        if not conn_record:
            raise ValueError("Database connection configuration not found")
        
        url = ""
        if conn_record.db_type == 'mysql':
            # mysql+pymysql://user:password@host:port/dbname
            url = f"mysql+pymysql://{conn_record.username}:{conn_record.password}@{conn_record.host}:{conn_record.port}/{conn_record.database_name}"
        elif conn_record.db_type == 'postgres':
            # postgresql+psycopg2://user:password@host:port/dbname
            url = f"postgresql+psycopg2://{conn_record.username}:{conn_record.password}@{conn_record.host}:{conn_record.port}/{conn_record.database_name}"
        else:
            raise ValueError(f"Unsupported database type: {conn_record.db_type}")
        
        return create_engine(url)
    
    raise ValueError("No data source provided (file_id or connection_id)")

def get_db_schema_from_engine(engine) -> str:
    """Universal schema extractor using SQLAlchemy Inspector"""
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    
    schema_str = ""
    for table in table_names:
        schema_str += f"Table: {table}\nColumns: "
        columns = inspector.get_columns(table)
        col_strs = []
        for col in columns:
            col_type = str(col['type'])
            col_strs.append(f"{col['name']} ({col_type})")
        schema_str += ", ".join(col_strs) + "\n\n"
        
    return schema_str

def execute_query_with_engine(engine, sql_query: str):
    """Execute SQL using SQLAlchemy engine"""
    try:
        # Use pandas to read SQL (handles connection opening/closing)
        with engine.connect() as conn:
            # Pandas read_sql requires a connection object or sqlalchemy engine
            df = pd.read_sql_query(text(sql_query), conn)
            
        columns = df.columns.tolist()
        # Convert timestamp/date objects to string for JSON serialization
        df = df.applymap(lambda x: str(x) if isinstance(x, (pd.Timestamp, pd.Timedelta)) else x)
        data = df.to_dict(orient='records')
        return {"columns": columns, "data": data, "error": None}
    except Exception as e:
        return {"columns": [], "data": [], "error": str(e)}

# Backward compatibility for existing file-based calls in router (if any left)
def get_db_schema(db_path: str) -> str:
    engine = create_engine(f"sqlite:///{db_path}")
    return get_db_schema_from_engine(engine)

def execute_query(db_path: str, sql_query: str):
    engine = create_engine(f"sqlite:///{db_path}")
    return execute_query_with_engine(engine, sql_query)

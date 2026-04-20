import os
import re
import ast
import json
import pandas as pd
from datetime import datetime
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

from crypto_utils import encrypt_data, tokenize_data, decrypt_data
from utils import load_schema_from_json

DOTENV_PATH = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=DOTENV_PATH)

# Import multi-database manager
try:
    from multi_db_config import get_multi_db_manager
    MULTI_DB_AVAILABLE = True
except ImportError:
    MULTI_DB_AVAILABLE = False
    print("Warning: Multi-database support not available. Using single database mode.")

def get_db_engine(db_type: str = "postgresql"):
    """Get database engine for specific type (defaults to postgresql for backward compatibility)"""
    if MULTI_DB_AVAILABLE:
        return get_multi_db_manager().get_engine(db_type)
    else:
        # Fallback to original single database mode
        database_url = os.getenv("DATABASE_URL")
        if not database_url: 
            raise ValueError("DATABASE_URL not set in .env file")
        return create_engine(database_url)

def get_all_db_engines():
    """Get all available database engines"""
    if MULTI_DB_AVAILABLE:
        return get_multi_db_manager().get_all_engines()
    else:
        # Return single engine in a dict for compatibility
        return {"postgresql": get_db_engine()}

def sanitize_name(name: str, is_class=False) -> str:
    if is_class:
        name = re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()
        name = re.sub(r'_base$|_create$|_update$|_response$|_query$|_request$', '', name)
        if not name.endswith('s'):
            if name.endswith('y'): name = name[:-1] + 'ies'
            else: name += 's'
    name = name.lower()
    name = re.sub(r'\.csv$', '', name).replace(' ', '_')
    name = re.sub(r'[^a-z0-9_]', '', name).strip('_')
    return name

def create_schema(conn, schema_name: str):
    conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}";'))
    print(f"Schema '{schema_name}' is ready.")

def initialize_metadata_catalog(conn):
    conn.execute(text("CREATE TABLE IF NOT EXISTS public.upload_catalog (id SERIAL PRIMARY KEY, original_filename VARCHAR(255) NOT NULL, database_schema VARCHAR(255) NOT NULL UNIQUE, upload_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP, row_count INTEGER, column_count INTEGER, status VARCHAR(50), error_message TEXT);"))
    print("Metadata catalog 'public.upload_catalog' is ready.")

def initialize_audit_trail(conn):
    conn.execute(text("CREATE TABLE IF NOT EXISTS public.audit_trail (id SERIAL PRIMARY KEY, timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP, actor VARCHAR(100) NOT NULL, action VARCHAR(100) NOT NULL, status VARCHAR(50) NOT NULL, target_resource VARCHAR(255), details JSONB);"))
    print("Audit trail table 'public.audit_trail' is ready.")

def log_audit_event(conn, actor: str, action: str, status: str, target_resource: str = None, details: dict = None):
    conn.execute(text("INSERT INTO public.audit_trail (actor, action, status, target_resource, details) VALUES (:actor, :action, :status, :target_resource, :details);"), {"actor": actor, "action": action, "status": status, "target_resource": target_resource, "details": json.dumps(details) if details else None})

def log_upload_start(conn, filename: str, schema_name: str, row_count: int, col_count: int) -> int:
    result = conn.execute(text("INSERT INTO public.upload_catalog (original_filename, database_schema, row_count, column_count, status) VALUES (:filename, :schema_name, :row_count, :col_count, 'PENDING') RETURNING id;"), {"filename": filename, "schema_name": schema_name, "row_count": row_count, "col_count": col_count})
    return result.scalar_one()

def update_upload_log(conn, log_id: int, status: str, error_message: str = None):
    conn.execute(text("UPDATE public.upload_catalog SET status = :status, error_message = :error_message, upload_timestamp = CURRENT_TIMESTAMP WHERE id = :log_id;"), {"log_id": log_id, "status": status, "error_message": error_message})

def map_python_to_sql_type(py_type: str) -> str:
    return "TEXT"

def parse_pydantic_schema(pydantic_code: str) -> dict:
    tables = {}
    try: tree = ast.parse(pydantic_code)
    except SyntaxError as e: print(f"!!! FATAL: LLM generated invalid Python code. Error: {e} !!!"); return {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and any(b.id == 'BaseModel' for b in node.bases if isinstance(b, ast.Name)):
            table_name = sanitize_name(node.name, is_class=True)
            if table_name not in tables: tables[table_name] = {'columns': {}, 'source_fields': set()}
            for item in node.body:
                if isinstance(item, ast.AnnAssign):
                    if item.target.id.lower() == 'id':
                        continue
                    tables[table_name]['source_fields'].add(item.target.id)
                    py_type = ""
                    if isinstance(item.annotation, ast.Name): py_type = item.annotation.id
                    elif isinstance(item.annotation, ast.Subscript): py_type = getattr(item.annotation.slice, 'id', 'list')
                    tables[table_name]['columns'][sanitize_name(item.target.id)] = py_type
    return tables

def create_relational_tables(conn, schema_name: str, table_definitions: dict):
    for table_name, definition in table_definitions.items():
        if not definition['columns']: continue
        full_table_name = f'"{schema_name}"."{table_name}"'
        conn.execute(text(f'DROP TABLE IF EXISTS {full_table_name} CASCADE;'))
        cols_sql = [f'"{col_name}" {map_python_to_sql_type(py_type)}' for col_name, py_type in definition['columns'].items()]
        create_stmt = f'CREATE TABLE {full_table_name} (id SERIAL PRIMARY KEY, {", ".join(cols_sql)});'
        print(f"Executing: {create_stmt}")
        conn.execute(text(create_stmt))

def _apply_protection_policy(value: str, protection_level: str, role: str, use_basic: bool, use_partial: bool) -> str:
    """Helper function to apply the correct data protection based on policies."""
    if use_basic and use_partial:
        if protection_level == 'SENSITIVE': return encrypt_data(value, role=role)
        if protection_level == 'INTERNAL': return tokenize_data(value)
        return encrypt_data(value, role='admin')
    if use_basic:
        if protection_level == 'SENSITIVE': return encrypt_data(value, role=role)
        if protection_level == 'INTERNAL': return tokenize_data(value)
    elif use_partial:
        if protection_level == 'SENSITIVE': return encrypt_data(value, role=role)
    return value

def insert_relational_data(conn, schema_name: str, df: pd.DataFrame, table_definitions: dict, classification: dict, role: str, use_basic: bool, use_partial: bool):
    try:
        sorted_tables = sorted(table_definitions.items(), key=lambda item: len(item[1]['columns']))
        for index, row in df.iterrows():
            for table_name, definition in sorted_tables:
                data_to_insert = {}
                for py_col_name in definition['source_fields']:
                    original_df_col = next((c for c in classification.keys() if sanitize_name(c) == py_col_name), py_col_name)
                    if original_df_col in df.columns and pd.notna(row[original_df_col]):
                        value = str(row[original_df_col])
                        protection_level = classification.get(original_df_col, "PUBLIC")
                        processed_value = _apply_protection_policy(value, protection_level, role, use_basic, use_partial)
                        data_to_insert[sanitize_name(py_col_name)] = processed_value
                if data_to_insert:
                    full_table_name = f'"{schema_name}"."{table_name}"'
                    insert_cols = [f'"{name}"' for name in data_to_insert.keys()]
                    placeholders = [f":{name}" for name in data_to_insert.keys()]
                    insert_stmt = text(f'INSERT INTO {full_table_name} ({", ".join(insert_cols)}) VALUES ({", ".join(placeholders)});')
                    conn.execute(insert_stmt, [data_to_insert])
    except Exception as e:
        print(f"Error during data insertion for {schema_name}: {e}")
        raise

def update_data_in_place(conn, schema_name: str, role: str, classification: dict, use_basic: bool, use_partial: bool):
    print(f"--- Performing in-place update for schema '{schema_name}' ---")
    tables_query = text("SELECT table_name FROM information_schema.tables WHERE table_schema = :schema")
    table_names = [row[0] for row in conn.execute(tables_query, {"schema": schema_name})]
    for table_name in table_names:
        full_table_name = f'"{schema_name}"."{table_name}"'
        rows_query = text(f"SELECT * FROM {full_table_name}")
        all_rows = conn.execute(rows_query).mappings().all()
        for row in all_rows:
            updated_values = {}
            row_id = row['id']
            for col_name, current_value in row.items():
                if col_name == 'id' or current_value is None: continue
                
                original_value = str(current_value)
                decrypted_value = decrypt_data(original_value, role=role)
                if decrypted_value.startswith("[DECRYPTION_ERROR"):
                    decrypted_value = decrypt_data(original_value, role='admin') 
                if not decrypted_value.startswith("[DECRYPTION_ERROR"):
                    original_value = decrypted_value
                
                original_col_name = next((k for k, v in classification.items() if sanitize_name(k) == col_name), col_name)
                protection_level = classification.get(original_col_name, "PUBLIC")
                
                processed_value = _apply_protection_policy(original_value, protection_level, role, use_basic, use_partial)
                
                if processed_value != current_value:
                    updated_values[col_name] = processed_value

            if updated_values:
                set_clause = ", ".join([f'"{k}" = :{k}' for k in updated_values.keys()])
                update_stmt = text(f"UPDATE {full_table_name} SET {set_clause} WHERE id = :id")
                params = updated_values
                params['id'] = row_id
                conn.execute(update_stmt, params)
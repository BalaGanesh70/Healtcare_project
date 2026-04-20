import os
import re
import ast
import json
import hashlib
import pandas as pd
from datetime import datetime
from pathlib import Path
from sqlalchemy import text
from dotenv import load_dotenv

from crypto_utils import encrypt_data, tokenize_data, decrypt_data
from utils import load_schema_from_json
from multi_db_config import get_multi_db_manager

# MongoDB
try:
    from pymongo import MongoClient
except Exception:
    MongoClient = None

DOTENV_PATH = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=DOTENV_PATH)

MYSQL_DB_NAME = os.getenv('MYSQL_DB', 'healthcare_data')
MONGO_URI = os.getenv('MONGO_URI')
MONGO_DB_NAME = os.getenv('MONGO_DB')

_mongo_client = None

def _get_mongo_db():
    global _mongo_client
    if not MongoClient or not MONGO_URI or not MONGO_DB_NAME:
        return None
    if _mongo_client is None:
        _mongo_client = MongoClient(MONGO_URI)
    return _mongo_client[MONGO_DB_NAME]


def _mysql_safe_table_name(prefix: str, table_name: str) -> str:
    base = f"{prefix}_{table_name}"
    if len(base) <= 64:
        return base
    digest = hashlib.sha1(base.encode('utf-8')).hexdigest()[:8]
    keep = 64 - 1 - 8
    short = base[:keep]
    return f"{short}_{digest}"


def create_schema_multi_db(schema_name: str):
    """Create schema in all databases and prepare Mongo collections namespace"""
    db_manager = get_multi_db_manager()
    results = {}
    
    for db_type, engine in db_manager.get_all_engines().items():
        try:
            with engine.connect() as connection:
                with connection.begin():
                    if db_type == "sqlite":
                        print(f"SQLite schema '{schema_name}' is ready (using table prefixes).")
                        results[db_type] = {"status": "success", "message": "Schema ready (using table prefixes)"}
                    elif db_type == "mysql":
                        print(f"MySQL schema '{schema_name}' will be emulated via table prefixes in `{MYSQL_DB_NAME}`.")
                        results[db_type] = {"status": "success", "message": f"Schema emulated in {MYSQL_DB_NAME}"}
                    else:  # postgresql
                        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}";'))
                        print(f"Schema '{schema_name}' is ready in {db_type}.")
                        results[db_type] = {"status": "success", "message": "Schema created"}
        except Exception as e:
            print(f"Error creating schema in {db_type}: {e}")
            results[db_type] = {"status": "error", "error": str(e)}
    
    # MongoDB (no-op schema creation)
    try:
        mongo_db = _get_mongo_db()
        if mongo_db is not None:
            results['mongo'] = {"status": "success", "message": "Schema emulated via collection prefixes"}
    except Exception as e:
        results['mongo'] = {"status": "error", "error": str(e)}
    
    return results


def initialize_metadata_catalog_multi_db():
    """Initialize metadata catalog table in all databases (not used in Mongo)"""
    db_manager = get_multi_db_manager()
    results = {}
    
    for db_type, engine in db_manager.get_all_engines().items():
        try:
            with engine.connect() as connection:
                with connection.begin():
                    if db_type == "sqlite":
                        connection.execute(text("CREATE TABLE IF NOT EXISTS upload_catalog (id INTEGER PRIMARY KEY AUTOINCREMENT, original_filename VARCHAR(255) NOT NULL, database_schema VARCHAR(255) NOT NULL UNIQUE, upload_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, row_count INTEGER, column_count INTEGER, status VARCHAR(50), error_message TEXT);"))
                    elif db_type == "mysql":
                        connection.execute(text("CREATE TABLE IF NOT EXISTS upload_catalog (id INT AUTO_INCREMENT PRIMARY KEY, original_filename VARCHAR(255) NOT NULL, database_schema VARCHAR(255) NOT NULL UNIQUE, upload_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, row_count INT, column_count INT, status VARCHAR(50), error_message TEXT);"))
                    else:  # postgresql
                        connection.execute(text("CREATE TABLE IF NOT EXISTS public.upload_catalog (id SERIAL PRIMARY KEY, original_filename VARCHAR(255) NOT NULL, database_schema VARCHAR(255) NOT NULL UNIQUE, upload_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP, row_count INTEGER, column_count INTEGER, status VARCHAR(50), error_message TEXT);"))
                    
                    print(f"Metadata catalog 'upload_catalog' is ready in {db_type}.")
                    results[db_type] = {"status": "success", "message": "Metadata catalog initialized"}
        except Exception as e:
            print(f"Error initializing metadata catalog in {db_type}: {e}")
            results[db_type] = {"status": "error", "error": str(e)}
    
    # Mongo: not maintaining an upload catalog collection for now
    return results


def initialize_audit_trail_multi_db():
    """Initialize audit trail table in all databases (Mongo uses a collection)"""
    db_manager = get_multi_db_manager()
    results = {}
    
    for db_type, engine in db_manager.get_all_engines().items():
        try:
            with engine.connect() as connection:
                with connection.begin():
                    if db_type == "sqlite":
                        connection.execute(text("CREATE TABLE IF NOT EXISTS audit_trail (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, actor VARCHAR(100) NOT NULL, action VARCHAR(100) NOT NULL, status VARCHAR(50) NOT NULL, target_resource VARCHAR(255), details TEXT);"))
                    elif db_type == "mysql":
                        connection.execute(text("CREATE TABLE IF NOT EXISTS audit_trail (id INT AUTO_INCREMENT PRIMARY KEY, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, actor VARCHAR(100) NOT NULL, action VARCHAR(100) NOT NULL, status VARCHAR(50) NOT NULL, target_resource VARCHAR(255), details JSON);"))
                    else:  # postgresql
                        connection.execute(text("CREATE TABLE IF NOT EXISTS public.audit_trail (id SERIAL PRIMARY KEY, timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP, actor VARCHAR(100) NOT NULL, action VARCHAR(100) NOT NULL, status VARCHAR(50) NOT NULL, target_resource VARCHAR(255), details JSONB);"))
                    
                    print(f"Audit trail table 'audit_trail' is ready in {db_type}.")
                    results[db_type] = {"status": "success", "message": "Audit trail initialized"}
        except Exception as e:
            print(f"Error initializing audit trail in {db_type}: {e}")
            results[db_type] = {"status": "error", "error": str(e)}
    
    # Mongo audit collection on demand at insert time
    return results


def log_audit_event_multi_db(actor: str, action: str, status: str, target_resource: str = None, details: dict = None):
    """Log audit event in all databases"""
    db_manager = get_multi_db_manager()
    results = {}
    
    for db_type, engine in db_manager.get_all_engines().items():
        try:
            with engine.connect() as connection:
                with connection.begin():
                    if db_type == "postgresql":
                        connection.execute(text("INSERT INTO public.audit_trail (actor, action, status, target_resource, details) VALUES (:actor, :action, :status, :target_resource, :details);"), {"actor": actor, "action": action, "status": status, "target_resource": target_resource, "details": json.dumps(details) if details else None})
                    else:
                        connection.execute(text("INSERT INTO audit_trail (actor, action, status, target_resource, details) VALUES (:actor, :action, :status, :target_resource, :details);"), {"actor": actor, "action": action, "status": status, "target_resource": target_resource, "details": json.dumps(details) if details else None})
                    
                    results[db_type] = {"status": "success", "message": "Audit event logged"}
        except Exception as e:
            print(f"Error logging audit event in {db_type}: {e}")
            results[db_type] = {"status": "error", "error": str(e)}
    
    # Mongo
    try:
        mongo_db = _get_mongo_db()
        if mongo_db is not None:
            mongo_db['audit_trail'].insert_one({
                'timestamp': datetime.utcnow().isoformat(),
                'actor': actor,
                'action': action,
                'status': status,
                'target_resource': target_resource,
                'details': details or None,
            })
            results['mongo'] = {"status": "success", "message": "Audit event logged"}
    except Exception as e:
        results['mongo'] = {"status": "error", "error": str(e)}
    
    return results


def create_relational_tables_multi_db(schema_name: str, table_definitions: dict):
    """Create relational tables/collections in all databases"""
    db_manager = get_multi_db_manager()
    results = {}
    
    for db_type, engine in db_manager.get_all_engines().items():
        try:
            with engine.connect() as connection:
                with connection.begin():
                    for table_name, definition in table_definitions.items():
                        if not definition['columns']: continue
                        
                        if db_type == "sqlite":
                            full_table_name = f"{schema_name}_{table_name}"
                            cols_sql = [f'"{col_name}" TEXT' for col_name, py_type in definition['columns'].items()]
                            create_stmt = f'CREATE TABLE IF NOT EXISTS "{full_table_name}" (id INTEGER PRIMARY KEY AUTOINCREMENT, {", ".join(cols_sql)});'
                        elif db_type == "mysql":
                            safe = _mysql_safe_table_name(schema_name, table_name)
                            full_table_name = f"`{MYSQL_DB_NAME}`.`{safe}`"
                            cols_sql = [f'`{col_name}` TEXT' for col_name, py_type in definition['columns'].items()]
                            create_stmt = f'CREATE TABLE IF NOT EXISTS {full_table_name} (id INT AUTO_INCREMENT PRIMARY KEY, {", ".join(cols_sql)});'
                        else:  # postgresql
                            full_table_name = f'"{schema_name}"."{table_name}"'
                            cols_sql = [f'"{col_name}" TEXT' for col_name, py_type in definition['columns'].items()]
                            create_stmt = f'CREATE TABLE IF NOT EXISTS {full_table_name} (id SERIAL PRIMARY KEY, {", ".join(cols_sql)});'
                        
                        print(f"Executing on {db_type}: {create_stmt}")
                        connection.execute(text(create_stmt))
                    
                    results[db_type] = {"status": "success", "message": "Tables created"}
        except Exception as e:
            print(f"Error creating tables in {db_type}: {e}")
            results[db_type] = {"status": "error", "error": str(e)}
    
    # Mongo: create collections if not exist
    try:
        mongo_db = _get_mongo_db()
        if mongo_db is not None:
            for table_name, definition in table_definitions.items():
                if not definition['columns']: continue
                coll_name = f"{schema_name}_{table_name}"
                if coll_name not in mongo_db.list_collection_names():
                    mongo_db.create_collection(coll_name)
            results['mongo'] = {"status": "success", "message": "Collections created"}
    except Exception as e:
        results['mongo'] = {"status": "error", "error": str(e)}
    
    return results


def insert_relational_data_multi_db(schema_name: str, df: pd.DataFrame, table_definitions: dict, classification: dict, role: str, use_basic: bool, use_partial: bool):
    """Insert relational data/documents in all databases"""
    db_manager = get_multi_db_manager()
    results = {}
    
    for db_type, engine in db_manager.get_all_engines().items():
        try:
            with engine.connect() as connection:
                with connection.begin():
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
                                if db_type == "sqlite":
                                    full_table_name = f'"{schema_name}_{table_name}"'
                                elif db_type == "mysql":
                                    safe = _mysql_safe_table_name(schema_name, table_name)
                                    full_table_name = f"`{MYSQL_DB_NAME}`.`{safe}`"
                                else:  # postgresql
                                    full_table_name = f'"{schema_name}"."{table_name}"'
                                
                                insert_cols = [f'"{name}"' if db_type != "mysql" else f'`{name}`' for name in data_to_insert.keys()]
                                named_placeholders = [f":{name}" for name in data_to_insert.keys()]
                                insert_stmt = text(f'INSERT INTO {full_table_name} ({", ".join(insert_cols)}) VALUES ({", ".join(named_placeholders)});')
                                
                                connection.execute(insert_stmt, data_to_insert)
                    
                    results[db_type] = {"status": "success", "message": "Data inserted"}
        except Exception as e:
            print(f"Error inserting data in {db_type}: {e}")
            results[db_type] = {"status": "error", "error": str(e)}
    
    # Mongo: insert documents
    try:
        mongo_db = _get_mongo_db()
        if mongo_db is not None:
            sorted_tables = sorted(table_definitions.items(), key=lambda item: len(item[1]['columns']))
            for index, row in df.iterrows():
                for table_name, definition in sorted_tables:
                    doc = {}
                    for py_col_name in definition['source_fields']:
                        original_df_col = next((c for c in classification.keys() if sanitize_name(c) == py_col_name), py_col_name)
                        if original_df_col in df.columns and pd.notna(row[original_df_col]):
                            value = str(row[original_df_col])
                            protection_level = classification.get(original_df_col, "PUBLIC")
                            processed_value = _apply_protection_policy(value, protection_level, role, use_basic, use_partial)
                            doc[sanitize_name(py_col_name)] = processed_value
                    if doc:
                        coll = mongo_db[f"{schema_name}_{table_name}"]
                        coll.insert_one(doc)
            results['mongo'] = {"status": "success", "message": "Data inserted"}
    except Exception as e:
        results['mongo'] = {"status": "error", "error": str(e)}
    
    return results


def update_data_in_place_mongo(schema_name: str, role: str, classification: dict, use_basic: bool, use_partial: bool):
    """Apply protection policy in-place for all Mongo documents under a schema prefix."""
    mongo_db = _get_mongo_db()
    if mongo_db is None:
        return {"status": "skipped", "message": "MongoDB not configured"}
    updated = 0
    collections = [name for name in mongo_db.list_collection_names() if name.startswith(f"{schema_name}_")]
    for coll_name in collections:
        coll = mongo_db[coll_name]
        for doc in coll.find({}):
            set_updates = {}
            for col_name, current_value in list(doc.items()):
                if col_name == '_id' or current_value is None:
                    continue
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
                    set_updates[col_name] = processed_value
            if set_updates:
                coll.update_one({'_id': doc['_id']}, {'$set': set_updates})
                updated += 1
    return {"status": "success", "updated_docs": updated}


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


def sanitize_name(name: str, is_class=False) -> str:
    """Sanitize names for database compatibility"""
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


def get_all_schemas_multi_db():
    """Get all schemas from all databases"""
    db_manager = get_multi_db_manager()
    all_schemas = {}
    
    for db_type, engine in db_manager.get_all_engines().items():
        try:
            with engine.connect() as connection:
                if db_type == "sqlite":
                    result = connection.execute(text("SELECT DISTINCT substr(name, 1, instr(name, '_') - 1) as schema_name FROM sqlite_master WHERE type='table' AND name LIKE '%_%'"))
                    schemas = [row[0] for row in result if row[0]]
                elif db_type == "mysql":
                    result = connection.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = :db"), {"db": MYSQL_DB_NAME})
                    prefixes = set()
                    for row in result:
                        name = row[0]
                        if '_' in name:
                            prefixes.add(name.split('_', 1)[0])
                    schemas = sorted(prefixes)
                else:  # postgresql
                    result = connection.execute(text("SELECT schema_name FROM information_schema.schemata WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast', 'public') AND schema_name NOT LIKE 'pg_temp_%' AND schema_name NOT LIKE 'pg_toast_temp_%' ORDER BY schema_name"))
                    schemas = [row[0] for row in result]
                
                all_schemas[db_type] = schemas
        except Exception as e:
            print(f"Error getting schemas from {db_type}: {e}")
            all_schemas[db_type] = []
    
    # Mongo
    try:
        mongo_db = _get_mongo_db()
        if mongo_db is not None:
            prefixes = set()
            for name in mongo_db.list_collection_names():
                if '_' in name:
                    prefixes.add(name.split('_', 1)[0])
            all_schemas['mongo'] = sorted(prefixes)
    except Exception as e:
        all_schemas['mongo'] = []
    
    return all_schemas


def test_all_connections():
    """Test all database connections"""
    status = get_multi_db_manager().test_connections()
    try:
        mongo_db = _get_mongo_db()
        status['mongo'] = mongo_db is not None
    except Exception:
        status['mongo'] = False
    return status

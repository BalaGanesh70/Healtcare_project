import os
import re
import pandas as pd
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import List, Dict
from sqlalchemy import text
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from key_manager import load_keys_from_env, check_and_rotate_keys
from utils import (
    classify_data_by_role, generate_schema_by_role,
    store_schema_in_json, load_schema_from_json
)
from db_utils import (
    get_db_engine, create_schema, sanitize_name, initialize_metadata_catalog,
    log_upload_start, update_upload_log, parse_pydantic_schema,
    create_relational_tables, insert_relational_data,
    initialize_audit_trail, log_audit_event, update_data_in_place
)

# Import multi-database utilities
try:
    from multi_db_utils import (
        create_schema_multi_db, initialize_metadata_catalog_multi_db,
        initialize_audit_trail_multi_db, log_audit_event_multi_db,
        create_relational_tables_multi_db, insert_relational_data_multi_db,
        get_all_schemas_multi_db, test_all_connections, update_data_in_place_mongo
    )
    MULTI_DB_AVAILABLE = True
    print("Multi-database support enabled")
except ImportError:
    MULTI_DB_AVAILABLE = False
    print("Multi-database support not available, using single database mode")

app = FastAPI(title="Healthcare Platform with 24-Hour Auto Key & Salt Rotation", version="25.0.0-final")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def on_startup():
    print("--- Application starting up... ---")
    try:
        load_keys_from_env()
        check_and_rotate_keys()
        
        if MULTI_DB_AVAILABLE:
            # Initialize all databases (MySQL, SQLite)
            print("--- Initializing multi-database setup... ---")
            init_results = initialize_metadata_catalog_multi_db()
            print(f"Metadata catalog initialization: {init_results}")
            
            audit_results = initialize_audit_trail_multi_db()
            print(f"Audit trail initialization: {audit_results}")
            
            # Test all connections
            connection_status = test_all_connections()
            print(f"Database connection status: {connection_status}")
        else:
            # Fallback to single database (PostgreSQL)
            print("--- Initializing single database setup (PostgreSQL)... ---")
            engine = get_db_engine()
            with engine.connect() as connection, connection.begin():
                initialize_metadata_catalog(connection)
                initialize_audit_trail(connection)
        
        scheduler = BackgroundScheduler(timezone=pytz.UTC)
        scheduler.add_job(check_and_rotate_keys, trigger=IntervalTrigger(hours=24))
        scheduler.start()
        
        print("--- Key rotation check complete. Future checks scheduled every 24 hours. ---")
    except Exception as e:
        print(f"CRITICAL STARTUP ERROR: {e}")
        import sys
        sys.exit(1)
    print("--- Application startup complete. ---")

@app.post("/upload_and_provision/", status_code=202)
async def upload_and_provision(file: UploadFile = File(...), use_basic: bool = Form(...), use_partial: bool = Form(...)):
    if not file.filename.endswith('.csv'): 
        raise HTTPException(status_code=400, detail="File must be a CSV")
    try: 
        df = pd.read_csv(file.file)
    except Exception as e: 
        raise HTTPException(status_code=400, detail=f"Error reading CSV: {str(e)}")
    
    base_name = os.path.splitext(file.filename)[0]
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    upload_schema_name = sanitize_name(f"{base_name}_{timestamp}")
    provisioning_results = {}
    
    if MULTI_DB_AVAILABLE:
        # Log audit event in all databases
        audit_results = log_audit_event_multi_db(
            actor="SystemUploader", 
            action="PROVISION_DATA", 
            status="INITIATED", 
            target_resource=file.filename, 
            details={"protection_basic": use_basic, "protection_partial": use_partial, "target_base_schema": upload_schema_name}
        )
        print(f"Multi-database audit logging: {audit_results}")
    else:
        # Fallback to single database
        engine = get_db_engine()
        with engine.connect() as connection, connection.begin():
            log_audit_event(conn=connection, actor="SystemUploader", action="PROVISION_DATA", status="INITIATED", target_resource=file.filename, details={"protection_basic": use_basic, "protection_partial": use_partial, "target_base_schema": upload_schema_name})
    
    roles = ["doctor", "admin", "analyst", "staff", "researcher"]
    any_role_failed = False
    
    for role in roles:
        role_schema_name = f"{upload_schema_name}_{role}"
        
        try:
            if MULTI_DB_AVAILABLE:
                # Create schema and tables in MySQL/SQLite (PostgreSQL not modified)
                schema_results = create_schema_multi_db(role_schema_name)
                print(f"Schema creation results for {role}: {schema_results}")
                
                classification = classify_data_by_role(df, role)
                pydantic_code = generate_schema_by_role(classification, role, df)
                print(f"--- LLM Output for role '{role}' ---\n{pydantic_code}\n----------------------------------")
                store_schema_in_json(role, role_schema_name, pydantic_code, classification)
                table_definitions = parse_pydantic_schema(pydantic_code)
                if not table_definitions: 
                    raise ValueError(f"LLM failed to generate a parsable Pydantic model for role '{role}'.")
                
                table_results = create_relational_tables_multi_db(role_schema_name, table_definitions)
                print(f"Table creation results for {role}: {table_results}")
                data_results = insert_relational_data_multi_db(
                    role_schema_name, df, table_definitions, classification, 
                    role, use_basic, use_partial
                )
                print(f"Data insertion results for {role}: {data_results}")
            else:
                # Fallback to single database (PostgreSQL)
                engine = get_db_engine()
                with engine.connect() as connection, connection.begin():
                    create_schema(connection, role_schema_name)
                    log_id = log_upload_start(connection, f"{file.filename} ({role})", role_schema_name, len(df), len(df.columns))
                    classification = classify_data_by_role(df, role)
                    pydantic_code = generate_schema_by_role(classification, role, df)
                    print(f"--- LLM Output for role '{role}' ---\n{pydantic_code}\n----------------------------------")
                    store_schema_in_json(role, role_schema_name, pydantic_code, classification)
                    table_definitions = parse_pydantic_schema(pydantic_code)
                    if not table_definitions: 
                        raise ValueError(f"LLM failed to generate a parsable Pydantic model for role '{role}'.")
                    create_relational_tables(connection, role_schema_name, table_definitions)
                    insert_relational_data(conn=connection, schema_name=role_schema_name, df=df, table_definitions=table_definitions, classification=classification, role=role, use_basic=use_basic, use_partial=use_partial)
                    update_upload_log(connection, log_id, "SUCCESS")
            
            provisioning_results[role] = {"status": "Success", "schema_created": role_schema_name}
            
        except Exception as e:
            any_role_failed = True
            import traceback
            traceback.print_exc()
            provisioning_results[role] = {"status": "Failed", "error": str(e)}

    final_status = "PARTIAL_FAILURE" if any_role_failed else "SUCCESS"
    
    if MULTI_DB_AVAILABLE:
        # Log final status across MySQL/SQLite only
        log_audit_event_multi_db(
            actor="SystemUploader", action="PROVISION_DATA", 
            status=final_status, target_resource=file.filename, details=provisioning_results
        )
    else:
        # Fallback to single database
        engine = get_db_engine()
        with engine.connect() as connection, connection.begin():
            log_audit_event(conn=connection, actor="SystemUploader", action="PROVISION_DATA", status=final_status, target_resource=file.filename, details=provisioning_results)
    
    if any_role_failed:
        return JSONResponse(status_code=207, content={"message": "Schema provisioning process completed with one or more failures.", "provisioning_results": provisioning_results})
    
    return JSONResponse(status_code=200, content={"message": f"Schema provisioning process completed successfully.", "provisioning_results": provisioning_results})

@app.get("/all-db-schemas/", response_model=List[str])
async def get_all_db_schemas():
    if MULTI_DB_AVAILABLE:
        all_schemas = get_all_schemas_multi_db()
        # Prefer PostgreSQL (full schema names), then MySQL (prefix emulation), then SQLite
        for preferred in ["postgresql", "mysql", "sqlite"]:
            schemas = all_schemas.get(preferred)
            if schemas:
                # Filter out internal/system names when using emulated lists
                filtered = [s for s in schemas if s not in ["upload", "upload_catalog", "audit", "audit_trail", "public"]]
                return filtered
        return []
    else:
        engine = get_db_engine()
        with engine.connect() as connection:
            query = text("SELECT schema_name FROM information_schema.schemata WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast', 'public') AND schema_name NOT LIKE 'pg_temp_%' AND schema_name NOT LIKE 'pg_toast_temp_%' ORDER BY schema_name;")
            result = connection.execute(query)
            return [row[0] for row in result]

@app.get("/schema-details/{schema_name}", response_model=Dict)
async def get_schema_details(schema_name: str):
    schema_data = load_schema_from_json(schema_name)
    if not schema_data:
        raise HTTPException(status_code=404, detail=f"No stored schema details found for schema ID '{schema_name}'.")
    return schema_data

@app.post("/update-protection/", status_code=202)
async def update_schema_protection(schemas_to_update: List[str] = Form(...), use_basic: bool = Form(...), use_partial: bool = Form(...)):
    update_results = {}
    
    if MULTI_DB_AVAILABLE:
        log_audit_event_multi_db(
            actor="SchemaManager", action="UPDATE_PROTECTION", 
            status="INITIATED", details={"schemas_targeted": schemas_to_update, "new_protection_basic": use_basic, "new_protection_partial": use_partial}
        )
    else:
        # Fallback to single database
        engine = get_db_engine()
        with engine.connect() as connection, connection.begin():
            log_audit_event(conn=connection, actor="SchemaManager", action="UPDATE_PROTECTION", status="INITIATED", details={"schemas_targeted": schemas_to_update, "new_protection_basic": use_basic, "new_protection_partial": use_partial})
    
    any_schema_failed = False
    for schema_name in schemas_to_update:
        try:
            schema_details = load_schema_from_json(schema_name)
            if not schema_details or 'classification' not in schema_details:
                raise ValueError(f"No stored classification plan found for schema '{schema_name}'. Cannot update.")
            classification = schema_details['classification']
            role = schema_details.get('role', "")
            
            if MULTI_DB_AVAILABLE:
                # Apply in-place protection policy across all databases
                for db_type in ["postgresql", "mysql", "sqlite"]:
                    try:
                        engine = get_db_engine(db_type)
                        with engine.connect() as connection, connection.begin():
                            update_data_in_place(conn=connection, schema_name=schema_name, role=role, classification=classification, use_basic=use_basic, use_partial=use_partial)
                    except Exception as e:
                        print(f"Failed to update {schema_name} in {db_type}: {e}")
                        any_schema_failed = True
                # Mongo
                try:
                    mongo_res = update_data_in_place_mongo(schema_name=schema_name, role=role, classification=classification, use_basic=use_basic, use_partial=use_partial)
                    if mongo_res.get('status') == 'skipped':
                        print("Mongo update skipped (not configured)")
                except Exception as e:
                    print(f"Failed to update {schema_name} in mongo: {e}")
                    any_schema_failed = True
            else:
                # Fallback to single database
                engine = get_db_engine()
                with engine.connect() as connection, connection.begin():
                    update_data_in_place(conn=connection, schema_name=schema_name, role=role, classification=classification, use_basic=use_basic, use_partial=use_partial)
            
            update_results[schema_name] = {"status": "Success"}
            
        except Exception as e:
            any_schema_failed = True
            update_results[schema_name] = {"status": "Failed", "error": str(e)}

    final_status = "PARTIAL_FAILURE" if any_schema_failed else "SUCCESS"
    
    if MULTI_DB_AVAILABLE:
        log_audit_event_multi_db(
            actor="SchemaManager", action="UPDATE_PROTECTION", 
            status=final_status, details=update_results
        )
    else:
        # Fallback to single database
        engine = get_db_engine()
        with engine.connect() as connection, connection.begin():
            log_audit_event(conn=connection, actor="SchemaManager", action="UPDATE_PROTECTION", status=final_status, details=update_results)
    
    return JSONResponse(status_code=207 if any_schema_failed else 200, content={"message": f"Protection update completed.", "results": update_results})

@app.post("/withdraw-schemas/", status_code=200)
async def withdraw_specific_schemas(schemas_to_delete: List[str] = Form(...)):
    if not schemas_to_delete:
        raise HTTPException(status_code=400, detail="No schemas provided for withdrawal.")
    
    results = {"deleted_db": [], "failed_db": []}
    
    if MULTI_DB_AVAILABLE:
        log_audit_event_multi_db(
            actor="SchemaManager", action="WITHDRAW_SCHEMAS", 
            status="INITIATED", details={"schemas_targeted": schemas_to_delete}
        )
    else:
        # Fallback to single database
        engine = get_db_engine()
        with engine.connect() as connection, connection.begin():
            log_audit_event(conn=connection, actor="SchemaManager", action="WITHDRAW_SCHEMAS", status="INITIATED", details={"schemas_targeted": schemas_to_delete})
    
    try:
        if MULTI_DB_AVAILABLE:
            # Withdraw from PostgreSQL, MySQL, SQLite, Mongo
            for db_type in ["postgresql", "mysql", "sqlite"]:
                try:
                    engine = get_db_engine(db_type)
                    with engine.connect() as connection, connection.begin():
                        for schema_name in schemas_to_delete:
                            if not re.match(r'^[a-z0-9_]+$', schema_name):
                                results["failed_db"].append(f"{schema_name} - Invalid schema name format.")
                                continue
                            try:
                                if db_type == "sqlite":
                                    tables_query = text("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE :schema_pattern")
                                    tables = [row[0] for row in connection.execute(tables_query, {"schema_pattern": f"{schema_name}_%"})]
                                    for table in tables:
                                        connection.execute(text(f'DROP TABLE IF EXISTS "{table}";'))
                                elif db_type == "mysql":
                                    tables_query = text("SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name LIKE :prefix")
                                    tables = [row[0] for row in connection.execute(tables_query, {"prefix": f"{schema_name}_%"})]
                                    for table in tables:
                                        connection.execute(text(f"DROP TABLE IF EXISTS `{table}`;"))
                                else:  # postgresql
                                    connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE;'))
                                    connection.execute(text("DELETE FROM public.upload_catalog WHERE database_schema = :schema"), {"schema": schema_name})
                                
                                results["deleted_db"].append(schema_name)
                            except Exception as e:
                                results["failed_db"].append(f"{schema_name} - Error: {str(e)}")
                except Exception as e:
                    print(f"Failed to withdraw schemas from {db_type}: {e}")
            # Mongo
            try:
                from multi_db_utils import _get_mongo_db
                mongo_db = _get_mongo_db()
                if mongo_db is not None:
                    for schema_name in schemas_to_delete:
                        for coll_name in [name for name in mongo_db.list_collection_names() if name.startswith(f"{schema_name}_")]:
                            mongo_db.drop_collection(coll_name)
                        results["deleted_db"].append(schema_name)
            except Exception as e:
                results["failed_db"].append(f"mongo - Error: {str(e)}")
        else:
            # Fallback to single database
            engine = get_db_engine()
            with engine.connect() as connection, connection.begin():
                for schema_name in schemas_to_delete:
                    if not re.match(r'^[a-z0-9_]+$', schema_name):
                        results["failed_db"].append(f"{schema_name} - Invalid schema name format.")
                        continue
                    try:
                        connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE;'))
                        connection.execute(text("DELETE FROM public.upload_catalog WHERE database_schema = :schema"), {"schema": schema_name})
                        results["deleted_db"].append(schema_name)
                    except Exception as e:
                        results["failed_db"].append(f"{schema_name} - Error: {str(e)}")
        
        final_status = "SUCCESS" if not results["failed_db"] else "PARTIAL_FAILURE"
    except Exception as e:
        final_status = "CRITICAL_FAILURE"
        results["error"] = str(e)
    
    if MULTI_DB_AVAILABLE:
        log_audit_event_multi_db(
            actor="SchemaManager", action="WITHDRAW_SCHEMAS", 
            status=final_status, details=results
        )
    else:
        # Fallback to single database
        engine = get_db_engine()
        with engine.connect() as connection, connection.begin():
            log_audit_event(conn=connection, actor="SchemaManager", action="WITHDRAW_SCHEMAS", status=final_status, details=results)
    
    if final_status == "CRITICAL_FAILURE": 
        raise HTTPException(status_code=500, detail=results)
    if not results["deleted_db"] and results["failed_db"]: 
        raise HTTPException(status_code=400, detail={"message": "All schema withdrawals failed.", "details": results})
    
    return JSONResponse(status_code=200, content={"message": "Schema withdrawal from database completed. Metadata files are preserved as a permanent record.", "details": results})

@app.get("/health")
async def health_check(): 
    return {"status": "healthy"}

@app.get("/db-status")
async def get_database_status():
    """Get status of all database connections"""
    if MULTI_DB_AVAILABLE:
        connection_status = test_all_connections()
        all_schemas = get_all_schemas_multi_db()
        return {
            "multi_db_enabled": True,
            "connection_status": connection_status,
            "schemas_by_database": all_schemas
        }
    else:
        return {
            "multi_db_enabled": False,
            "message": "Single database mode (PostgreSQL only)"
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
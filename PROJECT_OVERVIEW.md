# PrivacyWeave - Project Overview

## 1. ABSTRACT
PrivacyWeave is a healthcare data security platform that protects patient datasets during upload, storage, and access workflows. It combines machine learning based data classification with policy-driven protection methods such as encryption and tokenization. The system helps teams provision secure schemas, update protection levels, and maintain audit-ready governance using a simple frontend and automated backend services.

## 2. PROBLEM DESCRIPTION
Healthcare organizations manage clinical datasets containing highly sensitive information such as patient identifiers, diagnoses, and treatment records. In many systems, privacy controls are inconsistent because data sensitivity is handled manually and schema provisioning is not standardized.

Major challenges include:

- inconsistent protection across datasets,
- manual and error-prone preprocessing,
- limited audit visibility for schema changes,
- difficulty applying different protection levels for different data roles.

PrivacyWeave addresses these issues by creating a centralized workflow: upload data, classify attributes, apply selected protection policies, generate schemas, and record operations in metadata/audit systems. This reduces compliance risk and improves trust in healthcare data handling.

## 3. MODEL USED
The project uses a pre-trained machine learning classifier to categorize healthcare data fields by role/sensitivity. These predictions are used by the backend to decide how each field should be protected under selected policy options.

- **Backend:** FastAPI service for upload handling, provisioning endpoints, schema operations, and governance logic.
- **Frontend:** Streamlit interface enabling secure user workflows for provisioning and policy updates.
- **Data/Storage Layer:** Relational and multi-database utilities for schema creation, metadata cataloging, and audit trail persistence.
- **Security Components:** Key management, cryptographic utilities, and scheduled key/salt rotation checks for continuous protection.

This model-first approach improves consistency, reduces manual errors, and supports scalable privacy automation for repeated data ingestion workflows.

## 4. SAMPLE IMPORTANT CODE 

### Sample from `backend/main.py`
```python
@app.on_event("startup")
def on_startup():
    print("--- Application starting up... ---")
    try:
        load_keys_from_env()
        check_and_rotate_keys()
        
        if MULTI_DB_AVAILABLE:
            # Initialize all databases (MySQL, SQLite)
            print("--- Initializing multi-database setup... ---")
```

### Sample from `frontend/app.py`
```python
@st.cache_data(ttl=10)
def get_all_db_schemas():
    try:
        response = requests.get(f"{API_BASE_URL}/all-db-schemas/")
        if response.status_code == 200: return response.json()
        return []
    except Exception as e: st.error(f"Failed to connect to backend: {e}"); return None

def fetch_schema_details(schema_name):
    if schema_name in st.session_state.schema_details_cache: return st.session_state.schema_details_cache[schema_name]
```

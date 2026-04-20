import streamlit as st
import requests
import re
import pandas as pd

st.set_page_config(page_title="Healthcare Data Security Platform", page_icon="⚕️", layout="wide")
st.title("⚕️ Healthcare Data Security Platform")
st.markdown("Provision, manage, and govern the lifecycle of secure healthcare data schemas with role-based access control and encryption.")

API_BASE_URL = "http://localhost:8000"

if 'provision_use_basic' not in st.session_state: st.session_state.provision_use_basic = False
if 'provision_use_partial' not in st.session_state: st.session_state.provision_use_partial = True
if 'update_use_basic' not in st.session_state: st.session_state.update_use_basic = False
if 'update_use_partial' not in st.session_state: st.session_state.update_use_partial = True
if 'schema_details_cache' not in st.session_state: st.session_state.schema_details_cache = {}
if 'last_withdraw_message' not in st.session_state: st.session_state.last_withdraw_message = None
if 'last_provision_message' not in st.session_state: st.session_state.last_provision_message = None

@st.cache_data(ttl=10)
def get_all_db_schemas():
    try:
        response = requests.get(f"{API_BASE_URL}/all-db-schemas/")
        if response.status_code == 200: return response.json()
        return []
    except Exception as e: st.error(f"Failed to connect to backend: {e}"); return None

def fetch_schema_details(schema_name):
    if schema_name in st.session_state.schema_details_cache: return st.session_state.schema_details_cache[schema_name]
    try:
        response = requests.get(f"{API_BASE_URL}/schema-details/{schema_name}")
        if response.status_code == 200:
            details = response.json(); st.session_state.schema_details_cache[schema_name] = details; return details
        return {"error": f"Details not found (Status: {response.status_code})"}
    except Exception: return {"error": "Could not connect to backend to fetch details."}

def display_consent_widgets(context: str):
    basic_key = f"{context}_use_basic"; partial_key = f"{context}_use_partial"
    st.session_state[partial_key] = st.checkbox("Partial Protection", value=st.session_state[partial_key], help="Encrypts SENSITIVE data only.", key=f"cb_partial_{context}")
    st.session_state[basic_key] = st.checkbox("Basic Protection", value=st.session_state[basic_key], help="Encrypts SENSITIVE data and tokenizes INTERNAL data.", key=f"cb_basic_{context}")
    st.info("If both are checked, ALL data (SENSITIVE, INTERNAL, PUBLIC) will be protected.")

with st.expander("▶️ 1. Provision New Dataset", expanded=True):
    new_file = st.file_uploader("Upload New Healthcare CSV", type="csv", key="provisioning_uploader")
    if new_file:
        st.success(f"Dataset '{new_file.name}' uploaded successfully!")
        st.subheader("Set Initial Protection Level")
        display_consent_widgets("provision")
        
        if st.button("🚀 Start Provisioning Process", use_container_width=True, type="primary"):
            with st.spinner("Applying protection and generating schemas..."):
                new_file.seek(0)
                files = {'file': (new_file.name, new_file, 'text/csv')}
                data = {'use_basic': st.session_state.provision_use_basic, 'use_partial': st.session_state.provision_use_partial}
                response = requests.post(f"{API_BASE_URL}/upload_and_provision/", files=files, data=data)
                if response.status_code in [200, 202, 207]:
                    st.session_state.last_provision_message = "**Schema provisioning process completed successfully!**"
                    st.session_state.schema_details_cache.clear()
                    st.rerun()
                else: st.error(f"Server Error: {response.status_code} - {response.text}")
        
        if st.session_state.last_provision_message:
            st.success(st.session_state.last_provision_message)
            st.session_state.last_provision_message = None

st.divider()
st.header("2. Manage Existing Schemas")

all_db_schemas = get_all_db_schemas()

if all_db_schemas is None: st.warning("Could not load schemas from the backend.")
elif not all_db_schemas: st.info("No schemas exist in the database yet.")
else:
    def on_action_change(): st.session_state.last_withdraw_message = None
    action = st.selectbox("Choose a management action:", ["---", "Update Protection", "Withdraw Schemas"], on_change=on_action_change)
    
    if action == "Update Protection":
        st.subheader("Step 1: Select Schemas to Update")
        update_selected_schemas = st.multiselect("Select one or more schemas:", options=all_db_schemas, key="update_multiselect")
        if update_selected_schemas:
            st.subheader("Step 2: Review Selected Schemas")
            for schema in update_selected_schemas:
                details = fetch_schema_details(schema)
                with st.expander(f"Details for `{schema}`"):
                    st.write("**AI-Generated Protection Plan:**")
                    st.json(details.get('classification', {}))
            st.divider()
            st.subheader("Step 3: Set New Protection Level")
            display_consent_widgets("update")
            if st.button("Apply New Protection to Selected Schemas"):
                with st.spinner("Applying new protection settings..."):
                    form_data = [('schemas_to_update', s) for s in update_selected_schemas]
                    form_data.append(('use_basic', str(st.session_state.update_use_basic)))
                    form_data.append(('use_partial', str(st.session_state.update_use_partial)))
                    response = requests.post(f"{API_BASE_URL}/update-protection/", data=form_data)
                    if response.status_code in [200, 202, 207]: 
                        st.success(f"**Protection update completed!**")
                        st.rerun()
                    else: st.error(f"Update failed: {response.status_code} - {response.text}")

    elif action == "Withdraw Schemas":
        st.subheader("Step 1: Select Schemas to Withdraw")
        selected_for_withdrawal = st.multiselect("Select one or more schemas:", options=all_db_schemas, key="withdraw_selector")
        
        if st.session_state.last_withdraw_message:
            st.success(st.session_state.last_withdraw_message)
            st.session_state.last_withdraw_message = None
        
        if selected_for_withdrawal:
            st.subheader("Step 2: Review Selected Schemas")
            for schema in selected_for_withdrawal:
                details = fetch_schema_details(schema)
                with st.expander(f"Details for `{schema}`"):
                    st.write("**AI-Generated Protection Plan:**")
                    st.json(details.get('classification', {}))
            st.divider()
            st.subheader("Step 3: Confirm Withdrawal")
            st.warning("⚠️ **DANGER ZONE:** You are about to permanently delete the selected database schemas and all their data.")
            
            def handle_withdraw():
                payload = [('schemas_to_delete', s) for s in selected_for_withdrawal]
                with st.spinner("Withdrawing schemas from the database..."):
                    response = requests.post(f"{API_BASE_URL}/withdraw-schemas/", data=payload)
                if response.status_code == 200:
                    deleted_list = ", ".join(f"`{s}`" for s in selected_for_withdrawal)
                    st.session_state.last_withdraw_message = f"**Schema withdrawal completed successfully!** The following schemas were removed: {deleted_list}."
                    st.session_state.schema_details_cache.clear()
                else: 
                    st.session_state.last_withdraw_message = f"Withdrawal failed: {response.text}"
            
            st.button("Confirm and Permanently Withdraw Schemas", type="primary", on_click=handle_withdraw)


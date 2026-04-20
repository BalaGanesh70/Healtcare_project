import openai
import os
import json
import joblib
import pandas as pd
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# --- Setup Paths and Environment ---
DOTENV_PATH = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=DOTENV_PATH)
openai.api_key = os.getenv("OPENAI_API_KEY")

SCHEMAS_DIR = Path(__file__).resolve().parent / "schemas"
SCHEMAS_DIR.mkdir(exist_ok=True)

ROLES = ["doctor", "admin", "analyst", "staff", "researcher"]

# --- ML Classifier Setup ---
CLASSIFIER_PATH = Path(__file__).resolve().parent / "data_classifier.joblib"
CLASSIFIER_MODEL = None
LABEL_ENCODER = None

def load_classifier():
    """Loads the pre-trained data classifier model and label encoder from disk."""
    global CLASSIFIER_MODEL, LABEL_ENCODER
    try:
        if CLASSIFIER_PATH.exists():
            data = joblib.load(CLASSIFIER_PATH)
            CLASSIFIER_MODEL = data['pipeline']
            LABEL_ENCODER = data['label_encoder']
            print("--- Offline Data Classifier loaded successfully. ---")
        else:
            print(f"--- WARNING: Classifier model not found at {CLASSIFIER_PATH}. Classification will be disabled. ---")
            print("--- Please run `python backend/train_classifier.py` to generate the model. ---")
    except Exception as e:
        print(f"--- CRITICAL ERROR loading classifier model: {e} ---")

# Load the model on application startup
load_classifier()


def classify_data_by_role(df, role):
    """
    Classifies data columns using a pre-trained offline ML model.
    """
    if not CLASSIFIER_MODEL or not LABEL_ENCODER:
        raise ValueError("Data classifier model is not loaded. Cannot perform classification.")

    columns = df.columns
    # Create a DataFrame in the format expected by the model pipeline
    prediction_df = pd.DataFrame({
        'role': [role] * len(columns),
        'column_name': columns
    })

    # Predict the encoded labels
    encoded_predictions = CLASSIFIER_MODEL.predict(prediction_df)
    
    # Decode the labels back to strings ('SENSITIVE', 'INTERNAL', 'PUBLIC')
    classifications = LABEL_ENCODER.inverse_transform(encoded_predictions)
    
    # Create the final dictionary mapping column names to classifications
    result = dict(zip(columns, classifications))
    
    print(f"Offline classification for role '{role}' complete.")
    return result

# NOTE: The function below still uses the LLM for Pydantic schema generation, as requested.
def generate_schema_by_role(classified_data, role, df):
    sample_data = df.head(3).to_dict('records')
    role_specific_prompts = {
        "doctor": """
Generate Pydantic model schemas for a doctor's medical system access. Include models for:
- Patient medical data requests/updates
- Diagnosis and prescription management
- Medical record access requests
Focus on medical workflow and patient care operations.
""",
        "admin": """
Generate Pydantic model schemas for an administrator's view of the uploaded data.
The admin role has full visibility into all data for auditing, management, and troubleshooting.
Your task is to create logical Pydantic models that represent a comprehensive, well-structured view of ALL available columns in the provided dataset.
Focus on creating a clear and complete representation of the uploaded data.
Do NOT invent fields; use only the columns from the dataset.
""",
        "analyst": """
Generate Pydantic model schemas for data analysis operations. Include models for:
- Report generation requests
- Data aggregation and statistics requests
- Anonymized data access requests
- Analytics dashboard configuration
Focus on data analysis and reporting workflows.
""",
        "staff": """
Generate Pydantic model schemas for healthcare staff operations. Include models for:
- Patient registration and basic information updates
- Appointment scheduling requests
- Basic patient data queries
- Staff operational requests
Focus on patient intake and basic healthcare operations.
""",
        "researcher": """
Generate Pydantic model schemas for research operations. Include models for:
- Research study data requests
- Anonymized dataset access requests
- Research protocol submissions
- Publication and findings submissions
Focus on research workflows and data anonymization.
"""
    }
    prompt = f"""
You are a Python developer creating Pydantic models for a healthcare data system.

Role: {role}
{role_specific_prompts.get(role, "Generate appropriate schemas for this healthcare role.")}

Available Data Columns and Classifications:
{json.dumps(classified_data, indent=2)}

Sample Data:
{json.dumps(sample_data, indent=2, default=str)}

Generate 3–5 Pydantic model classes for this role's access and operational needs.

STRICT CONSTRAINTS:
- Only include fields that exist in the dataset (`df.columns`) — no extra fields or invented fields.
- You may include optional metadata fields like `id`, `created_at`, or `updated_at`, but do NOT invent fields unrelated to the dataset.
- Do NOT include any field that is not in the dataset unless it's one of these: `id`, `created_at`, `updated_at`.

INSTRUCTIONS:
1. Use appropriate Python typing (e.g., `str`, `int`, `Optional[str]`, `datetime`)
2. Inherit from `BaseModel` (from Pydantic)
3. Add relevant optional/required fields based on the classification:
   - `SENSITIVE`: include only if this role has legitimate access
   - `INTERNAL`, `PUBLIC`: always include if needed
4. Group models logically (e.g., for create, update, response operations)
5. Include `Config` class with `orm_mode = True` where relevant

EXAMPLE OUTPUT FORMAT:
```python
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ExampleBase(BaseModel):
    name: str
    age: Optional[int]

class ExampleCreate(ExampleBase):
    created_at: Optional[datetime] = None

class ExampleResponse(ExampleBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True

Respond with valid Python code containing the Pydantic model definitions.
"""
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=2000
        )
        content = response.choices[0].message.content.strip()
        if content.startswith('```python'):
            content = content[9:-3].strip()
        elif content.startswith('```'):
            content = content[3:-3].strip()
        return content
    except Exception as e:
        print(f"CRITICAL LLM ERROR in generate_schema_by_role: {e}")
        raise ValueError(f"Failed to generate Pydantic schema from OpenAI. Original error: {e}")


def store_schema_in_json(role: str, role_schema_name: str, schema_code: str, classification: dict):
    schema_data = {
        "schema_id": role_schema_name,
        "role": role,
        "last_generated_at": datetime.now().isoformat(),
        "classification": classification,
        "pydantic_schema": schema_code
    }
    
    filepath = SCHEMAS_DIR / f"{role_schema_name}.json"
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(schema_data, f, indent=2, ensure_ascii=False)
        print(f"SUCCESS: Schema details for {role} saved to NEW file: {filepath}")
    except Exception as e:
        print(f"ERROR: Could not save schema to file {filepath}: {e}")
        
def load_schema_from_json(schema_name: str):
    filepath = SCHEMAS_DIR / f"{schema_name}.json"
    try:
        if filepath.exists():
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None
    except Exception as e:
        print(f"ERROR: Could not load schema from file {schema_name}: {e}")
        return None
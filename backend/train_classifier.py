import pandas as pd
import joblib
from pathlib import Path
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import OneHotEncoder, LabelEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix

def train_and_save_model():
    """
    Trains a classifier to determine data sensitivity based on column name and role,
    evaluates its performance in detail, and saves the trained model pipeline.
    """
    # Define file paths relative to this script
    script_dir = Path(__file__).parent
    data_path = script_dir / 'classification_training_data.csv'
    model_path = script_dir / 'data_classifier.joblib'

    print("--- Starting Data Classifier Training ---")

    # 1. Load Data
    try:
        df = pd.read_csv(data_path)
        print(f"Loaded {len(df)} records from {data_path}")
    except FileNotFoundError:
        print(f"CRITICAL: Training data '{data_path}' not found. Cannot train model.")
        return

    # 2. Preprocess Target Variable
    le = LabelEncoder()
    df['classification_encoded'] = le.fit_transform(df['classification'])
    class_names = list(le.classes_)
    print(f"Target classes found: {class_names}")

    # 3. Define Features (X) and Target (y)
    X = df[['role', 'column_name']]
    y = df['classification_encoded']

    # 4. Create a Preprocessing Pipeline for Features
    preprocessor = ColumnTransformer(
        transformers=[
            ('role', OneHotEncoder(handle_unknown='ignore'), ['role']),
            ('column', TfidfVectorizer(analyzer='char', ngram_range=(2, 5)), 'column_name')
        ],
        remainder='passthrough'
    )

    # 5. Create the Full Model Pipeline
    model_pipeline = Pipeline(steps=[
        ('preprocessor', preprocessor),
        ('classifier', RandomForestClassifier(n_estimators=100, random_state=42, class_weight='balanced'))
    ])

    # 6. Split data and Train the Model
    print("Splitting data and training the model...")
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)
    model_pipeline.fit(X_train, y_train)
    print("Training complete.")

    # --- DETAILED MODEL EVALUATION ---
    print("\n--- Evaluating Model Performance on Test Set ---")
    y_pred = model_pipeline.predict(X_test)

    # 7. Print Classification Report
    print("\nClassification Report:")
    report = classification_report(y_test, y_pred, target_names=class_names)
    print(report)

    # 8. Generate and Display Confusion Matrix
    print("Generating Confusion Matrix...")
    cm = confusion_matrix(y_test, y_pred)
    plt.figure(figsize=(10, 7))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues',
                xticklabels=class_names, yticklabels=class_names)
    plt.title('Confusion Matrix')
    plt.ylabel('Actual Class')
    plt.xlabel('Predicted Class')
    plt.tight_layout()
    # Save the matrix to a file for review
    confusion_matrix_path = script_dir / "confusion_matrix.png"
    plt.savefig(confusion_matrix_path)
    print(f"Confusion Matrix plot saved to: {confusion_matrix_path}")
    plt.show() # Also display it directly if in an interactive session
    
    # 9. Save the trained model
    print(f"\nSaving model pipeline to: {model_path}")
    joblib.dump({'pipeline': model_pipeline, 'label_encoder': le}, model_path)
    print("--- Model saved successfully. ---")


if __name__ == "__main__":
    train_and_save_model()
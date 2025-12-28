import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
import os

# Initialize Firestore
if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

def upload():
    file_path = 'students.csv'
    
    # Check if file exists
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found!")
        return

    try:
        # Load CSV - skipinitialspace helps with formatting issues
        df = pd.read_csv(file_path, skipinitialspace=True)
        
        if df.empty:
            print("Error: The CSV file is empty!")
            return

        print(f"Found {len(df)} students. Starting upload...")

        batch = db.batch()
        for index, row in df.iterrows():
            # Use ID as document ID
            doc_ref = db.collection('students').document(str(row['ID']))
            batch.set(doc_ref, {
                'ID': str(row['ID']),
                'Name': str(row['Name']),
                'Phone': str(row['Phone']),
                'Department': str(row['Department']),
                'Assigned_Group': int(row['Assigned_Group'])
            })
            
        batch.commit()
        print("Done! All students uploaded to Firestore.")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    upload()
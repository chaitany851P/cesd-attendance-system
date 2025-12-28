import pandas as pd
import io
import os
import json
from flask import Flask, render_template, request, redirect, url_for, session, send_file
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

app = Flask(__name__)
# IMPORTANT: Use a solid secret key for Hugging Face sessions
app.secret_key = os.getenv("SECRET_KEY", "cesd_ultra_secure_2025_9988")

# --- FIREBASE INITIALIZATION ---
try:
    firebase_secret = os.getenv("FIREBASE_CONFIG")
    if firebase_secret:
        print("✔ Found FIREBASE_CONFIG secret. Parsing...")
        cred_dict = json.loads(firebase_secret)
        cred = credentials.Certificate(cred_dict)
    else:
        print("⚠ FIREBASE_CONFIG not found. Looking for local JSON...")
        cred = credentials.Certificate("serviceAccountKey.json")

    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("✔ Firestore Connected Successfully!")
except Exception as e:
    print(f"❌ Firebase Initialization Error: {e}")

# Configuration
INSTRUCTORS = ["Ms. Khushali", "Mr. Dhruv"]
FACULTY_GROUPS = {
    "Ms. Yashvi Donga": [1, 2],
    "Ms. Khushi Jodhani": [4, 9],
    "Ms. Yashvi Kankotiya": [3],
    "Mr. Yug Shah": [5],
    "Ms. Darshana Nasit": [6],
    "Mr. Raj Vyas": [8, 10],
    "Mr. Mihir Rathod": [7],
    "Mr. Nihar Thakkar": [11, 12],
    "Mr. Chaitany Thakar": [13, 14],
    "Ms. Srushti Jasoliya": [15, 18],
    "Ms. Brinda Varsani": [16, 20],
    "Mr. Tirth Avaiya": [17, 19]
}
ALL_USERS = sorted(list(FACULTY_GROUPS.keys()) + INSTRUCTORS)

try:
    df_students = pd.read_csv('students.csv')
    print(f"✔ Students CSV Loaded: {len(df_students)} records")
except Exception as e:
    print(f"❌ CSV Load Error: {e}")

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user_name = request.form.get('faculty_name')
        print(f"Login attempt for: {user_name}") # DEBUG PRINT
        if user_name in ALL_USERS:
            session['faculty'] = user_name
            session['is_instructor'] = user_name in INSTRUCTORS
            print(f"Login successful. Redirecting to dashboard...") # DEBUG PRINT
            return redirect(url_for('dashboard'))
        else:
            print("Login failed: User not in list") # DEBUG PRINT
    return render_template('login.html', faculties=ALL_USERS)

@app.route('/dashboard')
def dashboard():
    if 'faculty' not in session:
        print("Dashboard access denied: No session") # DEBUG PRINT
        return redirect(url_for('login'))
    
    user = session['faculty']
    is_ins = session.get('is_instructor')
    groups = list(range(1, 21)) if is_ins else FACULTY_GROUPS.get(user, [])
    return render_template('dashboard.html', faculty=user, groups=groups, is_instructor=is_ins)

# ... Rest of your routes (mark_attendance, export_attendance, logout) same as before ...

@app.route('/mark_attendance/<int:group_no>', methods=['GET', 'POST'])
def mark_attendance(group_no):
    if 'faculty' not in session: return redirect(url_for('login'))
    group_students = df_students[df_students['Assigned_Group'] == group_no].to_dict('records')
    
    if request.method == 'POST':
        try:
            date = request.form.get('attendance_date')
            present_ids = request.form.getlist('status')
            batch = db.batch()
            for student in group_students:
                s_id = str(student['ID'])
                status = "Present" if s_id in present_ids else "Absent"
                doc_ref = db.collection('attendance').document(f"{date}_{s_id}")
                batch.set(doc_ref, {
                    'date': date, 'id': s_id, 'name': student['Name'], 
                    'department': student['Department'], 'group': group_no, 
                    'marked_by': session['faculty'], 'status': status,
                    'timestamp': firestore.SERVER_TIMESTAMP
                })
            batch.commit()
            return render_template('status.html', success=True, date=date, group_no=group_no)
        except Exception as e:
            return render_template('status.html', success=False, message=str(e))
    return render_template('mark_attendance.html', students=group_students, group_no=group_no)

@app.route('/export_attendance')
def export_attendance():
    if not session.get('is_instructor'): return "Denied", 403
    docs = db.collection('attendance').stream()
    data = [doc.to_dict() for doc in docs]
    if not data: return "No Records", 404
    
    df = pd.DataFrame(data)
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize(None)
    
    df = df.sort_values(by=['group', 'date', 'id'])
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Master_Group_Wise')
        for date_val, date_df in df.groupby('date'):
            sheet_name = f"Date_{str(date_val).replace('-', '_')}"
            date_df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
    output.seek(0)
    return send_file(output, download_name="CESD_Master_Report.xlsx", as_attachment=True)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    # HF typically requires port 7860
    app.run(host='0.0.0.0', port=7860)

import pandas as pd
import io
import os
import json
from flask import Flask, render_template, request, redirect, url_for, session, send_file
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

app = Flask(__name__)
app.secret_key = "cesd_final_v4_2025"

# --- 1. FIREBASE INITIALIZATION ---
firebase_secret = os.getenv("FIREBASE_CONFIG")
if firebase_secret:
    cred_dict = json.loads(firebase_secret)
    if 'private_key' in cred_dict:
        cred_dict['private_key'] = cred_dict['private_key'].replace('\\n', '\n')
    cred = credentials.Certificate(cred_dict)
else:
    cred = credentials.Certificate("serviceAccountKey.json")

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)
db = firestore.client()

# --- 2. CONFIGURATION ---
INSTRUCTORS = ["Ms. Khushali", "Mr. Dhruv"]
FACULTY_GROUPS = {
    "Ms. Yashvi Donga": [1, 2], "Ms. Yashvi Kankotiya": [3], "Ms. Khushi Jodhani": [4, 9],
    "Mr. Yug Shah": [5], "Ms. Darshana Nasit": [6], "Mr. Mihir Rathod": [7],
    "Mr. Raj Vyas": [8, 10], "Mr. Nihar Thakkar": [11, 12], "Mr. Chaitany Thakar": [13, 14],
    "Ms. Srushti Jasoliya": [15, 18], "Ms. Brinda Varsani": [16, 20], "Mr. Tirth Avaiya": [17, 19]
}
FACULTY_DEPARTMENTS = {
    "Mr. Nihar Thakkar": "AIML", "Ms. Yashvi Donga": "CE", "Ms. Yashvi Kankotiya": "CL",
    "Ms. Khushi Jodhani": "CS", "Ms. Darshana Nasit": "EC", "Mr. Yug Shah": "EE",
    "Mr. Mihir Rathod": "IT", "Ms. Brinda Varsani": "ME", "Mr. Raj Vyas": "DCE",
    "Ms. Srushti Jasoliya": "DCS", "Mr. Tirth Avaiya": "DIT", "Ms. Khushali": "ALL", "Mr. Dhruv": "ALL"
}
DEPT_LIST = sorted(['AIML','CE','CL','CS','EC','EE','IT','ME','DCE','DCS','DIT'])
ALL_USERS = sorted(list(set(list(FACULTY_GROUPS.keys()) + list(FACULTY_DEPARTMENTS.keys()) + INSTRUCTORS)))

try:
    df_students = pd.read_csv('students.csv')
    df_students['ID'] = df_students['ID'].astype(str)
    df_students = df_students.sort_values(by='ID')
except:
    df_students = pd.DataFrame()

# --- 3. ROUTES ---

@app.route('/')
def index():
    if 'faculty' in session: return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form.get('faculty_name')
        if user in ALL_USERS:
            session.clear()
            session['faculty'] = user
            session['is_instructor'] = user in INSTRUCTORS
            session.permanent = True
            return redirect(url_for('dashboard'))
    return render_template('login.html', faculties=ALL_USERS)

@app.route('/dashboard')
def dashboard():
    if 'faculty' not in session: return redirect(url_for('login'))
    user, is_ins = session['faculty'], session.get('is_instructor')
    groups = list(range(1, 21)) if is_ins else FACULTY_GROUPS.get(user, [])
    dept = FACULTY_DEPARTMENTS.get(user)
    return render_template('dashboard.html', faculty=user, groups=groups, dept=dept, dept_list=DEPT_LIST, is_instructor=is_ins)

@app.route('/mark_attendance/<int:group_no>', methods=['GET', 'POST'])
def mark_attendance(group_no):
    if 'faculty' not in session: return redirect(url_for('login'))
    data = df_students[df_students['Assigned_Group'] == group_no].to_dict('records')
    if request.method == 'POST': return handle_save(data, group_no, "Engagement")
    return render_template('mark_attendance.html', students=data, group_no=group_no)

@app.route('/mark_dept_attendance/<dept_name>', methods=['GET', 'POST'])
def mark_dept_attendance(dept_name):
    if 'faculty' not in session: return redirect(url_for('login'))
    data = df_students[df_students['Department'] == dept_name].to_dict('records')
    if request.method == 'POST': return handle_save(data, dept_name, "Academic")
    return render_template('mark_attendance.html', students=data, dept_name=dept_name)

def handle_save(student_list, ident, mode):
    try:
        date = request.form.get('attendance_date')
        sess = request.form.get('session_type')
        p_ids = request.form.getlist('status')
        batch = db.batch()
        for s in student_list:
            sid = str(s['ID'])
            status = "Present" if sid in p_ids else "Absent"
            # THIS UNIQUE ID PREVENTS DUPLICATES
            # Format: Date_StudentID_Session_Mode (e.g. 2025-12-28_25EC002_Morning_Academic)
            doc_id = f"{date}_{sid}_{sess}_{mode}"
            batch.set(db.collection('attendance').document(doc_id), {
                'date': date, 'id': sid, 'name': s['Name'], 'department': s['Department'],
                'mode': mode, 'section': ident, 'session': sess,
                'status': status, 'marked_by': session['faculty'], 
                'timestamp': firestore.SERVER_TIMESTAMP
            })
        batch.commit()
        return render_template('status.html', success=True, date=date)
    except Exception as e:
        return render_template('status.html', success=False, message=str(e))

@app.route('/export_attendance')
def export_attendance():
    if not session.get('is_instructor'): return "Denied", 403
    docs = [d.to_dict() for d in db.collection('attendance').stream()]
    if not docs: return "No data", 404
    df = pd.DataFrame(docs)
    if 'timestamp' in df.columns: df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize(None)
    
    # Sort for professional report
    df = df.sort_values(by=['mode', 'section', 'date', 'session', 'id'])
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Master_Report')
        # Split by Date for easy checking
        for d_val, d_df in df.groupby('date'):
            d_df.to_excel(writer, index=False, sheet_name=f"Date_{str(d_val).replace('-','_')}"[:31])
    output.seek(0)
    return send_file(output, download_name="CESD_Master_Attendance.xlsx", as_attachment=True)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=7860)

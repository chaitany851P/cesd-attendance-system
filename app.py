import pandas as pd
import io, os, json
from flask import Flask, render_template, request, redirect, url_for, session, send_file
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

app = Flask(__name__)
app.secret_key = "cesd_final_ultra_secure_99"

# 1. Firebase Initialization
firebase_secret = os.getenv("FIREBASE_CONFIG")
if firebase_secret:
    cred_dict = json.loads(firebase_secret)
    if 'private_key' in cred_dict: cred_dict['private_key'] = cred_dict['private_key'].replace('\\n', '\n')
    cred = credentials.Certificate(cred_dict)
else:
    cred = credentials.Certificate("serviceAccountKey.json")
if not firebase_admin._apps: firebase_admin.initialize_app(cred)
db = firestore.client()

# 2. Unified Faculty Mapping
INSTRUCTORS = ["Ms. Khushali", "Mr. Dhruv"]
FACULTY_GROUPS = {
    "Ms. Yashvi Donga": [1, 2], "Ms. Yashvi Kankotiya": [3], "Ms. Khushi Jodhani": [4, 9],
    "Mr. Yug Shah": [5], "Ms. Darshana Nasit": [6], "Mr. Mihir Rathod": [7],
    "Mr. Raj Vyas": [8, 10], "Mr. Nihar Thakkar": [11, 12], "Mr. Chaitany Thakar": [13, 14],
    "Ms. Srushti Jasoliya": [15, 18], "Ms. Brinda Varsani": [16, 20], "Mr. Tirth Avaiya": [17, 19]
}

# Unified Department mapping - Giving Mr. Chaitany Thakar access to EC
FACULTY_DEPARTMENTS = {
    "Mr. Nihar Thakkar": "AIML", "Ms. Yashvi Donga": "CE", "Ms. Yashvi Kankotiya": "CL",
    "Ms. Khushi Jodhani": "CS", "Ms. Darshana Nasit": "EC", "Mr. Yug Shah": "EE",
    "Mr. Mihir Rathod": "IT", "Ms. Brinda Varsani": "ME", "Mr. Raj Vyas": "DCE",
    "Ms. Srushti Jasoliya": "DCS", "Mr. Tirth Avaiya": "DIT",
    "Mr. Chaitany Thakar": "EC", # ACCESS TO EC DEPARTMENT ADDED
    "Ms. Khushali": "ALL", "Mr. Dhruv": "ALL"
}

DEPT_LIST = sorted(['AIML','CE','CL','CS','EC','EE','IT','ME','DCE','DCS','DIT'])
ALL_USERS = sorted(list(set(list(FACULTY_GROUPS.keys()) + list(FACULTY_DEPARTMENTS.keys()) + INSTRUCTORS)))

try:
    df_students = pd.read_csv('students.csv')
    df_students['ID'] = df_students['ID'].astype(str)
    df_students = df_students.sort_values(by='ID')
except: df_students = pd.DataFrame()

# 3. Routes
@app.route('/')
def index():
    if 'faculty' in session: return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form.get('faculty_name')
        if user in ALL_USERS:
            session.clear(); session['faculty'] = user
            session['is_instructor'] = user in INSTRUCTORS
            session.permanent = True; return redirect(url_for('dashboard'))
    return render_template('login.html', faculties=ALL_USERS)

@app.route('/dashboard')
def dashboard():
    if 'faculty' not in session: return redirect(url_for('login'))
    user, is_ins = session['faculty'], session.get('is_instructor')
    groups = list(range(1, 21)) if is_ins else FACULTY_GROUPS.get(user, [])
    dept = FACULTY_DEPARTMENTS.get(user)
    return render_template('dashboard.html', faculty=user, groups=groups, dept=dept, dept_list=DEPT_LIST, is_instructor=is_ins)

@app.route('/add_student', methods=['POST'])
def add_student():
    if session.get('faculty') != "Mr. Chaitany Thakar":
        return "Unauthorized", 403
    
    try:
        sid = request.form.get('student_id').strip().upper()
        name = request.form.get('name').strip().upper()
        dept = request.form.get('department').strip().upper()
        group = int(request.form.get('assigned_group'))
        
        # Save to Firestore
        db.collection('students').document(sid).set({
            'ID': sid,
            'Name': name,
            'Department': dept,
            'Assigned_Group': group
        })
        
        # Flash message could be added here if needed
        return redirect(url_for('admin_panel'))
    except Exception as e:
        return f"Failed to add student: {str(e)}", 500


@app.route('/mark_attendance/<int:group_no>', methods=['GET', 'POST'])
def mark_attendance(group_no):
    if 'faculty' not in session: return redirect(url_for('login'))
    data = df_students[df_students['Assigned_Group'] == group_no].sort_values('ID').to_dict('records')
    if request.method == 'POST': return save_data_logic(data, f"Group {group_no}", "Engagement")
    return render_template('mark_attendance.html', students=data, title=f"Group {group_no}")

@app.route('/mark_dept_attendance/<dept_name>', methods=['GET', 'POST'])
def mark_dept_attendance(dept_name):
    if 'faculty' not in session: return redirect(url_for('login'))
    data = df_students[df_students['Department'] == dept_name].sort_values('ID').to_dict('records')
    if request.method == 'POST': return save_data_logic(data, dept_name, "Academic")
    return render_template('mark_attendance.html', students=data, title=f"{dept_name} Dept")

def save_data_logic(student_list, ident, mode):
    try:
        date, sess = request.form.get('attendance_date'), request.form.get('session_type')
        p_ids, batch = request.form.getlist('status'), db.batch()
        for s in student_list:
            sid = str(s['ID']); status = "Present" if sid in p_ids else "Absent"
            doc_id = f"{date}_{sid}_{sess}_{mode}"
            batch.set(db.collection('attendance').document(doc_id), {
                'date': date, 'id': sid, 'name': s['Name'], 'department': s['Department'],
                'mode': mode, 'section': ident, 'session': sess,
                'status': status, 'marked_by': session['faculty'], 'timestamp': firestore.SERVER_TIMESTAMP
            })
        batch.commit(); return render_template('status.html', success=True, date=date)
    except Exception as e: return render_template('status.html', success=False, message=str(e))

@app.route('/admin')
def admin_panel():
    if session.get('faculty') != "Mr. Chaitany Thakar":
        return "Access Denied: Admin Privileges Required", 403
    
    # Fetch current students from Firestore to ensure we edit live data
    docs = db.collection('students').stream()
    students = [d.to_dict() for d in docs]
    # Sort by ID for the admin table
    students = sorted(students, key=lambda x: x['ID'])
    
    return render_template('admin.html', students=students)

@app.route('/update_student', methods=['POST'])
def update_student():
    if session.get('faculty') != "Mr. Chaitany Thakar":
        return "Unauthorized", 403
    
    try:
        sid = request.form.get('student_id')
        new_group = int(request.form.get('new_group'))
        new_dept = request.form.get('new_dept').upper()
        
        # Update live Firestore record
        db.collection('students').document(sid).update({
            'Assigned_Group': new_group,
            'Department': new_dept
        })
        
        # IMPORTANT: To make this permanent even after a server restart, 
        # you should manually update your students.csv later, 
        # or add code here to write to the CSV file.
        
        return redirect(url_for('admin_panel'))
    except Exception as e:
        return f"Update Failed: {str(e)}", 500

@app.route('/export_attendance')
def export_attendance():
    if not session.get('is_instructor'): return "Denied", 403
    try:
        docs = [d.to_dict() for d in db.collection('attendance').stream()]
        if not docs: return "No data", 404
        df = pd.DataFrame(docs)
        for c in ['mode','section','date','session','id','timestamp']:
            if c not in df.columns: df[c] = "N/A"
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce').dt.tz_localize(None)
        df = df.sort_values(by=['mode','section','date','session','id'])
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Master_Report')
            for d_val, d_df in df.groupby('date'):
                d_df.to_excel(writer, index=False, sheet_name=f"Date_{str(d_val).replace('-','_')}"[:31])
        output.seek(0); return send_file(output, download_name="CESD_Master_Attendance.xlsx", as_attachment=True)
    except Exception as e: return f"Export Error: {str(e)}"

@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('login'))

if __name__ == '__main__': app.run(host='0.0.0.0', port=7860)

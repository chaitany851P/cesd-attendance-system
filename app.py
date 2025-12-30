import pandas as pd
import io, os, json
from flask import Flask, render_template, request, redirect, url_for, session, send_file
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

app = Flask(__name__)
app.secret_key = "cesd_admin_system_2025_final"

# Hugging Face Session Fix
app.config.update(
    SESSION_COOKIE_SAMESITE='None',
    SESSION_COOKIE_SECURE=True,
    PERMANENT_SESSION_LIFETIME=86400
)

# --- 1. FIREBASE INITIALIZATION ---
firebase_secret = os.getenv("FIREBASE_CONFIG")
if firebase_secret:
    cred_dict = json.loads(firebase_secret)
    if 'private_key' in cred_dict: cred_dict['private_key'] = cred_dict['private_key'].replace('\\n', '\n')
    cred = credentials.Certificate(cred_dict)
else:
    cred = credentials.Certificate("serviceAccountKey.json")
if not firebase_admin._apps: firebase_admin.initialize_app(cred)
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
    "Ms. Srushti Jasoliya": "DCS", "Mr. Tirth Avaiya": "DIT",
    "Mr. Chaitany Thakar": "EC", "Ms. Khushali": "ALL", "Mr. Dhruv": "ALL"
}
DEPT_LIST = sorted(['AIML','CE','CL','CS','EC','EE','IT','ME','DCE','DCS','DIT'])
ALL_USERS = sorted(list(set(list(FACULTY_GROUPS.keys()) + list(FACULTY_DEPARTMENTS.keys()) + INSTRUCTORS)))
ADMIN_LIST = ["Mr. Chaitany Thakar", "Mr. Dhruv", "Ms. Khushali"]
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

# --- REAL-TIME ATTENDANCE ROUTES ---

@app.route('/mark_attendance/<int:group_no>', methods=['GET', 'POST'])
def mark_attendance(group_no):
    if 'faculty' not in session: return redirect(url_for('login'))
    # Fetch live from Firestore
    docs = db.collection('students').where('Assigned_Group', '==', group_no).stream()
    data = sorted([d.to_dict() for d in docs], key=lambda x: x['ID'])
    if request.method == 'POST': return save_data_logic(data, f"Group {group_no}", "Engagement")
    return render_template('mark_attendance.html', students=data, title=f"Group {group_no}")

@app.route('/mark_dept_attendance/<dept_name>', methods=['GET', 'POST'])
def mark_dept_attendance(dept_name):
    if 'faculty' not in session: return redirect(url_for('login'))
    # Fetch live from Firestore
    docs = db.collection('students').where('Department', '==', dept_name).stream()
    data = sorted([d.to_dict() for d in docs], key=lambda x: x['ID'])
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

# --- ADMIN PANEL ROUTES (EXCLUSIVE TO MR. CHAITANY THAKAR) ---

@app.route('/admin')
def admin_panel():
    # Allow all three admins
    if session.get('faculty') not in ADMIN_LIST: 
        return "Access Denied", 403
    
    docs = db.collection('students').stream()
    students = sorted([d.to_dict() for d in docs], key=lambda x: x['ID'])
    return render_template('admin.html', students=students)

@app.route('/add_student', methods=['POST'])
def add_student():
    if session.get('faculty') not in ADMIN_LIST: return "Denied", 403
    sid = request.form.get('student_id').strip().upper()
    db.collection('students').document(sid).set({
        'ID': sid, 'Name': request.form.get('name').strip().upper(),
        'Department': request.form.get('department').strip().upper(),
        'Assigned_Group': int(request.form.get('assigned_group'))
    })
    return redirect(url_for('admin_panel'))

@app.route('/update_student', methods=['POST'])
def update_student():
    if session.get('faculty') not in ADMIN_LIST: return "Denied", 403
    sid = request.form.get('student_id')
    db.collection('students').document(sid).update({
        'Assigned_Group': int(request.form.get('new_group')),
        'Department': request.form.get('new_dept').upper()
    })
    return redirect(url_for('admin_panel'))

@app.route('/delete_student/<sid>')
def delete_student(sid):
    if session.get('faculty') not in ADMIN_LIST: return "Denied", 403
    db.collection('students').document(sid).delete()
    return redirect(url_for('admin_panel'))

# --- EXPORT & LOGOUT ---

@app.route('/export_attendance')
def export_attendance():
    if not session.get('is_instructor'): return "Denied", 403
    try:
        docs = [d.to_dict() for d in db.collection('attendance').stream()]
        if not docs: return "No data", 404
        df = pd.DataFrame(docs)
        for c in ['mode','section','date','session','id']:
            if c not in df.columns: df[c] = "N/A"
        if 'timestamp' in df.columns: df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce').dt.tz_localize(None)
        df = df.sort_values(by=['mode','section','date','session','id'])
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Master_Report')
        output.seek(0); return send_file(output, download_name="CESD_Master_Attendance.xlsx", as_attachment=True)
    except Exception as e: return f"Error: {str(e)}"

@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('login'))

if __name__ == '__main__': app.run(host='0.0.0.0', port=7860)

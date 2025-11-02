# app.py  
from flask import Flask, render_template, request, redirect, url_for, flash, session, g, jsonify, make_response, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
from dotenv import load_dotenv
from openai import OpenAI
from datetime import datetime
import csv
from io import StringIO
from flask import send_from_directory
from werkzeug.utils import secure_filename



# --- Load environment variables first ---
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError("❌ OPENAI_API_KEY not found in .env")

# --- Initialize OpenAI client ---
client = OpenAI(api_key=OPENAI_API_KEY)

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SECRET_KEY'] = 'change-this-to-a-random-secret-key'
db_url = os.getenv("DATABASE_URL")
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://")

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ---------- Models ----------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fullname = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Exam(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.String(300))
    questions = db.relationship('Question', backref='exam', lazy=True)


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exam.id'), nullable=False)
    question_text = db.Column(db.String(500), nullable=False)
    option1 = db.Column(db.String(200), nullable=False)
    option2 = db.Column(db.String(200), nullable=False)
    option3 = db.Column(db.String(200), nullable=False)
    option4 = db.Column(db.String(200), nullable=False)
    correct_option = db.Column(db.String(200), nullable=False)


class Result(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    exam_id = db.Column(db.Integer, db.ForeignKey('exam.id'), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    date_taken = db.Column(db.DateTime, default=datetime.utcnow)

class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    uploader = db.relationship('User', backref='notes_uploaded') 
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)




# ---------- helpers ----------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please login to access this page.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.user or not g.user.is_admin:
            flash("Admin access required.", "danger")
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function


@app.before_request
def load_logged_in_user():
    g.user = None
    if 'user_id' in session:
        g.user = User.query.get(session['user_id'])

# ---------- Admin: Upload Notes ----------
@app.route('/upload_notes', methods=['GET', 'POST'])
@admin_required
def upload_notes():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        file = request.files.get('file')

        if not title or not file:
            flash("Please provide both a title and a file.", "danger")
            return redirect(url_for('upload_notes'))

        # Save file securely
        filename = secure_filename(file.filename)
        upload_path = os.path.join('uploads', filename)
        file.save(upload_path)

        new_note = Note(title=title, filename=filename, uploaded_by=g.user.id)
        db.session.add(new_note)
        db.session.commit()

        flash("✅ Note uploaded successfully!", "success")
        return redirect(url_for('view_notes'))

    return render_template('upload_notes.html')



# ---------- Routes ----------
@app.route('/')
def home():
    exams = Exam.query.all()
    return render_template('index.html', exams=exams)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        fullname = request.form.get('fullname', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not fullname or not email or not password or not confirm_password:
          flash("Please fill out all fields.", "danger")
          return redirect(url_for('register'))

        if password != confirm_password:
            flash("❌ Passwords does not match. Please try again.", "danger")
            return redirect(url_for('register'))
        
         # 🔹 NEW CHECK: Prevent registration with the same name (case-sensitive)
        existing_name = User.query.filter_by(fullname=fullname).first()
        if existing_name:
            flash("⚠ A user with this name already exists. Please use a different name.", "warning")
            return redirect(url_for('register'))

        existing = User.query.filter_by(email=email).first()
        if existing:
            flash("An account with that email already exists. Please log in.", "warning")
            return redirect(url_for('login'))

        user = User(fullname=fullname, email=email)
        user.set_password(password)
        db.session.add(user)
        
        try:
            db.session.commit()  # commit only if email unique
        except Exception as e:
            db.session.rollback()
            flash("Email already registered. Please log in instead.", "warning")
            return redirect(url_for('login'))


        flash("Registration successful. Please log in.", "success")
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            session.clear()
            session['user_id'] = user.id
            flash(f"Welcome, {user.fullname}!", "success")
            return redirect(url_for('home'))
        else:
            flash("Invalid email or password.", "danger")
            return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('home'))


@app.route('/exam')
@login_required
def exam():
    exams = Exam.query.all()
    if exams:
        return redirect(url_for('take_exam', exam_id=exams[0].id))
    flash("No exams available yet.", "info")
    return redirect(url_for('home'))


@app.route('/exam_list')
@login_required
def exam_list():
    exams = Exam.query.all()
    taken_exam_ids = [r.exam_id for r in Result.query.filter_by(user_id=g.user.id).all()]
    return render_template('exam_list.html', exams=exams, taken_exam_ids=taken_exam_ids)


@app.route('/chat')
@login_required
def chat():
    return render_template('chat.html')


@app.route('/chatbot', methods=['POST'])
@login_required
def chatbot():
    user_input = request.json.get('message', '').strip()

    if not user_input:
        return jsonify({"reply": "Please type a message."})

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are SmartBot, a helpful AI tutor for Smart E-Learning."},
                {"role": "user", "content": user_input}
            ],
            max_tokens=250,
            temperature=0.7
        )
        bot_reply = response.choices[0].message.content.strip()
        return jsonify({"reply": bot_reply})
    except Exception as e:
        print("OpenAI API Error:", e)
        return jsonify({"reply": "⚠ Sorry, I'm having trouble connecting to SmartBot."})


# ---------- Admin: Add Exam ----------
@app.route('/add_exam', methods=['GET', 'POST'])
@admin_required
def add_exam():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        desc = request.form.get('description', '').strip()
        
        if not title:
            flash("Exam title is required.", "danger")
            return redirect(url_for('add_exam'))

        new_exam = Exam(title=title, description=desc)
        db.session.add(new_exam)
        db.session.commit()
        flash("Exam added successfully! Now add questions.", "success")
        return redirect(url_for('add_question', exam_id=new_exam.id))

    return render_template('add_exam.html')


# ---------- Admin: Add Questions ----------
@app.route('/add_question/<int:exam_id>', methods=['GET', 'POST'])
@admin_required
def add_question(exam_id):
    exam = Exam.query.get_or_404(exam_id)

    if request.method == 'POST':
        question_text = request.form['question_text'].strip()
        option1 = request.form['option1'].strip()
        option2 = request.form['option2'].strip()
        option3 = request.form['option3'].strip()
        option4 = request.form['option4'].strip()
        correct_option = request.form['correct_option'].strip()

        options = [option1, option2, option3, option4]
        if correct_option not in options:
            flash("❌ Correct Option must exactly match one of the four options.", "danger")
            return redirect(url_for('add_question', exam_id=exam.id))

        new_question = Question(
            exam_id=exam.id,
            question_text=question_text,
            option1=option1,
            option2=option2,
            option3=option3,
            option4=option4,
            correct_option=correct_option
        )
        db.session.add(new_question)
        db.session.commit()

        flash("✅ Question added successfully!", "success")
        return redirect(url_for('add_question', exam_id=exam.id))

    return render_template('add_question.html', exam=exam)


@app.route('/delete_exam/<int:exam_id>', methods=['POST'])
@admin_required
def delete_exam(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    Question.query.filter_by(exam_id=exam.id).delete()
    Result.query.filter_by(exam_id=exam.id).delete()
    db.session.delete(exam)
    db.session.commit()
    flash(f"Exam '{exam.title}' deleted successfully.", "success")
    return redirect(url_for('exam_list'))


@app.route('/take_exam/<int:exam_id>', methods=['GET', 'POST'])
@login_required
def take_exam(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    questions = Question.query.filter_by(exam_id=exam.id).all()

    existing_result = Result.query.filter_by(user_id=g.user.id, exam_id=exam.id).first()
    if existing_result:
        flash("⚠ You have already taken this exam. You cannot retake it.", "warning")
        return redirect(url_for('exam_list'))

    if request.method == 'POST':
        score = 0
        for q in questions:
            selected = request.form.get(str(q.id))
            if selected and selected.strip().lower() == q.correct_option.strip().lower():
                score += 1

        result = Result(
            user_id=g.user.id,
            exam_id=exam.id,
            score=score,
            date_taken=datetime.now()
        )
        db.session.add(result)
        db.session.commit()

        session['last_score'] = score
        session['last_total'] = len(questions)
        flash(f"✅ Exam submitted! You scored {score} out of {len(questions)}.", "success")
        return redirect(url_for('result'))

    return render_template('exam.html', exam=exam, questions=questions)


@app.route('/result')
@login_required
def result():
    score = session.get('last_score', None)
    return render_template('result.html', score=score if score is not None else 0)


# ---------- Admin: View Exam Participants ----------
@app.route('/exam_participants/<int:exam_id>')
@admin_required
def exam_participants(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    results = db.session.query(Result, User).join(User, Result.user_id == User.id).filter(Result.exam_id == exam.id).all()
    total_participants = len(results)
    avg_score = round(sum(r[0].score for r in results) / total_participants, 2) if total_participants else 0
    return render_template(
        'exam_participants.html',
        exam=exam,
        results=results,
        total_participants=total_participants,
        avg_score=avg_score
    )


# ---------- Admin: Delete All Participants ----------
@app.route('/delete_participants/<int:exam_id>', methods=['POST'])
@admin_required
def delete_participants(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    results = Result.query.filter_by(exam_id=exam.id).all()

    if not results:
        flash("⚠ No participants found to delete.", "warning")
        return redirect(url_for('exam_participants', exam_id=exam.id))

    for r in results:
        db.session.delete(r)
    db.session.commit()

    flash(f"🗑 All participants for '{exam.title}' have been deleted successfully.", "info")
    return redirect(url_for('exam_participants', exam_id=exam.id))



# ---------- CLI Utilities ----------
@app.cli.command("init-db")
def init_db():
    db.create_all()
    print("Initialized the database.")


@app.cli.command("create-admin")
def create_admin():
    fullname = input("Full Name: ")
    email = input("Email: ")
    password = input("Password: ")

    existing = User.query.filter_by(email=email).first()
    if existing:
        print("Admin with this email already exists.")
        return

    admin = User(fullname=fullname, email=email, is_admin=True)
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    print(f"Admin user '{fullname}' created successfully!")

# ---------- View & Download Notes ----------
@app.route('/view_notes')
@login_required
def view_notes():
    notes = Note.query.order_by(Note.upload_date.desc()).all()
    return render_template('view_notes.html', notes=notes)


@app.route('/download/<filename>')
@login_required
def download_note(filename):
    return send_from_directory('uploads', filename, as_attachment=True)

# ---------- Admin: Delete Notes ----------
@app.route('/delete_note/<int:note_id>', methods=['POST'])
@admin_required
def delete_note(note_id):
    note = Note.query.get_or_404(note_id)
    file_path = os.path.join('uploads', note.filename)

    # Delete file if exists
    if os.path.exists(file_path):
        os.remove(file_path)

    # Delete record
    db.session.delete(note)
    db.session.commit()
    flash(f"🗑 Note '{note.title}' deleted successfully.", "info")
    return redirect(url_for('view_notes'))


if __name__ == '__main__':
    app.run(debug=True)
# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session, g
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
from dotenv import load_dotenv
from openai import OpenAI

# --- Load environment variables first ---
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError("❌ OPENAI_API_KEY not found in .env")

# --- Initialize OpenAI client ---
client = OpenAI(api_key=OPENAI_API_KEY)




basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
# SECRET KEY (change to a random strong key for production)
app.config['SECRET_KEY'] = 'change-this-to-a-random-secret-key'
# SQLite DB file
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'smart_elearning.db')
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

# ---------- Exam Models ----------
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

# run before requests to load user object
@app.before_request
def load_logged_in_user():
    g.user = None
    if 'user_id' in session:
        g.user = User.query.get(session['user_id'])

# ---------- Routes ----------
@app.route('/')
def home():
    exams = Exam.query.all()
    return render_template('index.html',exams=exams)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        fullname = request.form.get('fullname', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not fullname or not email or not password:
            flash("Please fill out all fields.", "danger")
            return redirect(url_for('register'))

        # check if user exists
        existing = User.query.filter_by(email=email).first()
        if existing:
            flash("An account with that email already exists. Please log in.", "warning")
            return redirect(url_for('login'))

        # create user
        user = User(fullname=fullname, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

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
            # login success
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

# protected example route
@app.route('/exam')
@login_required
def exam():
    # redirect to exam list or first exam
    exams = Exam.query.all()
    if exams:
        return redirect(url_for('take_exam', exam_id=exams[0].id))
    flash("No exams available yet.", "info")
    return redirect(url_for('home'))


@app.route('/chat')
@login_required
def chat():
    return render_template('chat.html')

@app.route('/chatbot', methods=['POST'])
@login_required
def chatbot():
    from flask import request, jsonify
    user_input = request.json.get('message', '').strip()

    if not user_input:
        return jsonify({"reply": "Please type a message."})

    try:
        # Use GPT API with new OpenAI client
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are SmartBot, a helpful AI tutor for Smart E-Learning. You assist students with exams, registration, and study guidance in a friendly, clear manner."},
                {"role": "user", "content": user_input}
            ],
            max_tokens=250,
            temperature=0.7
        )

        bot_reply = response.choices[0].message.content.strip()
        return jsonify({"reply": bot_reply})

    except Exception as e:
        print("OpenAI API Error:", e)
        return jsonify({"reply": "⚠️ Sorry, I'm having trouble connecting to SmartBot’s brain right now."})




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
        q_text = request.form.get('question_text')
        o1 = request.form.get('option1')
        o2 = request.form.get('option2')
        o3 = request.form.get('option3')
        o4 = request.form.get('option4')
        correct = request.form.get('correct_option')

        if not all([q_text, o1, o2, o3, o4, correct]):
            flash("Please fill all fields!", "warning")
            return redirect(url_for('add_question', exam_id=exam.id))

        q = Question(
            exam_id=exam.id,
            question_text=q_text,
            option1=o1,
            option2=o2,
            option3=o3,
            option4=o4,
            correct_option=correct
        )
        db.session.add(q)
        db.session.commit()
        flash("Question added successfully!", "success")
        return redirect(url_for('add_question', exam_id=exam.id))

    return render_template('add_question.html', exam=exam)

@app.route('/delete_exam/<int:exam_id>', methods=['POST'])
@admin_required  # make sure you have this decorator
def delete_exam(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    Question.query.filter_by(exam_id=exam.id).delete()
    Result.query.filter_by(exam_id=exam.id).delete()
    db.session.delete(exam)
    db.session.commit()
    flash(f"Exam '{exam.title}' deleted successfully.", "success")
    return redirect(url_for('home'))



@app.route('/take_exam/<int:exam_id>', methods=['GET', 'POST'])
@login_required
def take_exam(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    questions = Question.query.filter_by(exam_id=exam.id).all()

    if request.method == 'POST':
        score = 0
        for q in questions:
            selected = request.form.get(str(q.id))
            if selected == q.correct_option:
                score += 1

        # Save result
        result = Result(user_id=g.user.id, exam_id=exam.id, score=score)
        db.session.add(result)
        db.session.commit()

        session['last_score'] = score
        session['last_total'] = len(questions)
        flash(f"You scored {score} out of {len(questions)}", "info")
        return redirect(url_for('result'))

    return render_template('exam.html', exam=exam, questions=questions)


# Example result route (protected)
@app.route('/result')
@login_required
def result():
    # pass dummy score for now; later you'll compute real score
    score = session.get('last_score', None)
    return render_template('result.html', score=score if score is not None else 0)


# Utility to create the DB (run manually once)
@app.cli.command("init-db")
def init_db():
    """Initialize the database."""
    db.create_all()
    print("Initialized the database.")

@app.cli.command("create-admin")
def create_admin():
    """Create a default admin user (Windows-friendly input)."""
    
    fullname = input("Full Name: ")
    email = input("Email: ")
    password = input("Password: ")  # 👈 Windows-friendly input

    # Check if admin already exists
    existing = User.query.filter_by(email=email).first()
    if existing:
        print("Admin with this email already exists.")
        return

    admin = User(fullname=fullname, email=email, is_admin=True)
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    print(f"Admin user '{fullname}' created successfully!")




if __name__ == '__main__':
    app.run(debug=True)

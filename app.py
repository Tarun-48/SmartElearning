# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session, g
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os

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

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# ---------- helpers ----------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please login to access this page.", "warning")
            return redirect(url_for('login'))
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
    return render_template('index.html')

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
            flash("Invalid email or password.", "error")
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
    # you can render exam.html (we kept exam.html earlier); it will have access to g.user
    return render_template('exam.html')

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

if __name__ == '__main__':
    app.run(debug=True)

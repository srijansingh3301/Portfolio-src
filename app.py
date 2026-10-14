import os
import uuid
from datetime import timedelta, datetime, timezone
from functools import wraps

from flask import (Flask, render_template, request, jsonify, redirect,
                   url_for, session)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXT = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

app = Flask(__name__, static_folder='static', template_folder='templates')

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-this-to-a-long-random-string')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'site.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  

app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

ADMIN_EMAIL = "hiro@sboosts.com"
ADMIN_PASSWORD_HASH = generate_password_hash(
    os.environ.get('ADMIN_PASSWORD', 'HIROSIMHA')
)

db = SQLAlchemy(app)

class Thought(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'date': self.created_at.strftime('%b %d, %Y'),
        }

class Photo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(300), nullable=False)
    caption = db.Column(db.String(300), default='')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'url': url_for('static', filename='uploads/' + self.filename),
            'caption': self.caption or '',
            'date': self.created_at.strftime('%b %d, %Y'),
        }

with app.app_context():
    db.create_all()

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('admin'):
            if request.path.startswith('/admin/api'):
                return jsonify({'error': 'unauthorized'}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper

@app.route('/')
def index():
    return render_template('main.html')

@app.route('/api/thoughts')
def api_thoughts():
    thoughts = Thought.query.order_by(Thought.created_at.desc()).all()
    return jsonify([t.to_dict() for t in thoughts])

@app.route('/api/photos')
def api_photos():
    photos = Photo.query.order_by(Photo.created_at.desc()).all()
    return jsonify([p.to_dict() for p in photos])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('admin'):
        return redirect(url_for('admin'))
    error = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        if email == ADMIN_EMAIL.lower() and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session.permanent = True
            session['admin'] = True
            return redirect(url_for('admin'))
        error = 'Wrong email or password.'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/admin')
@login_required
def admin():
    return render_template('admin.html')

@app.route('/admin/api/thoughts', methods=['POST'])
@login_required
def create_thought():
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    content = (data.get('content') or '').strip()
    if not title or not content:
        return jsonify({'error': 'Title and content are required.'}), 400
    t = Thought(title=title, content=content)
    db.session.add(t)
    db.session.commit()
    return jsonify(t.to_dict()), 201

@app.route('/admin/api/thoughts/<int:tid>/delete', methods=['POST'])
@login_required
def delete_thought(tid):
    t = db.session.get(Thought, tid)
    if not t:
        return jsonify({'error': 'not found'}), 404
    db.session.delete(t)
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/admin/api/photos', methods=['POST'])
@login_required
def upload_photo():
    file = request.files.get('photo')
    caption = (request.form.get('caption') or '').strip()
    if not file or file.filename == '':
        return jsonify({'error': 'No file selected.'}), 400
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_EXT:
        return jsonify({'error': 'Only png, jpg, jpeg, gif, webp allowed.'}), 400
    filename = uuid.uuid4().hex + '.' + ext
    file.save(os.path.join(UPLOAD_FOLDER, filename))
    p = Photo(filename=filename, caption=caption)
    db.session.add(p)
    db.session.commit()
    return jsonify(p.to_dict()), 201

@app.route('/admin/api/photos/<int:pid>/delete', methods=['POST'])
@login_required
def delete_photo(pid):
    p = db.session.get(Photo, pid)
    if not p:
        return jsonify({'error': 'not found'}), 404
    try:
        os.remove(os.path.join(UPLOAD_FOLDER, p.filename))
    except OSError:
        pass
    db.session.delete(p)
    db.session.commit()
    return jsonify({'ok': True})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

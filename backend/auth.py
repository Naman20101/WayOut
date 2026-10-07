"""Local SQLite user accounts for WAYOUT.

Design choices:
  - No external service. One SQLite file lives under data/users.db.
  - Passwords hashed with werkzeug.security (PBKDF2-SHA256).
  - No email verification. Users pick a username; the app stores their
    home location so it can show hazards for that area on login.
  - No password recovery. If a user forgets, they create a new account —
    appropriate for a disaster-prep tool where the goal is speed of access.
"""
import sqlite3
from pathlib import Path
from werkzeug.security import generate_password_hash, check_password_hash

from backend.config import BASE_DIR

DB_PATH = BASE_DIR / 'data' / 'users.db'


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT,
                home_lat REAL,
                home_lon REAL,
                home_label TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS saved_locations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        conn.commit()


def create_user(username, password, display_name=None,
                home_lat=None, home_lon=None, home_label=None):
    init_db()
    username = (username or '').strip().lower()
    if not username or len(username) < 3:
        raise ValueError('Username must be at least 3 characters.')
    if not password or len(password) < 6:
        raise ValueError('Password must be at least 6 characters.')
    if not username.isalnum() and '_' not in username:
        raise ValueError('Username may contain letters, digits and underscores only.')
    pw_hash = generate_password_hash(password)
    try:
        with _connect() as conn:
            cur = conn.execute(
                'INSERT INTO users(username, password_hash, display_name, '
                'home_lat, home_lon, home_label) VALUES (?,?,?,?,?,?)',
                (username, pw_hash, display_name or username,
                 home_lat, home_lon, home_label))
            conn.commit()
            return cur.lastrowid
    except sqlite3.IntegrityError:
        raise ValueError('That username is already taken.')


def verify_user(username, password):
    username = (username or '').strip().lower()
    with _connect() as conn:
        row = conn.execute(
            'SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    if not row:
        return None
    if not check_password_hash(row['password_hash'], password):
        return None
    return dict(row)


def get_user(user_id):
    with _connect() as conn:
        row = conn.execute(
            'SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    return dict(row) if row else None


def update_home(user_id, lat, lon, label):
    with _connect() as conn:
        conn.execute(
            'UPDATE users SET home_lat=?, home_lon=?, home_label=? WHERE id=?',
            (lat, lon, label, user_id))
        conn.commit()


def add_saved_location(user_id, label, lat, lon):
    with _connect() as conn:
        conn.execute(
            'INSERT INTO saved_locations(user_id, label, lat, lon) '
            'VALUES (?,?,?,?)', (user_id, label, lat, lon))
        conn.commit()


def list_saved_locations(user_id):
    with _connect() as conn:
        rows = conn.execute(
            'SELECT * FROM saved_locations WHERE user_id=? '
            'ORDER BY created_at DESC', (user_id,)).fetchall()
    return [dict(r) for r in rows]


def delete_saved_location(user_id, loc_id):
    with _connect() as conn:
        conn.execute(
            'DELETE FROM saved_locations WHERE id=? AND user_id=?',
            (loc_id, user_id))
        conn.commit()
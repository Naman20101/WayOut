"""Short-lived MySQL connections; every user value is parameterised."""
from contextlib import contextmanager
import mysql.connector
from backend.config import db_config

@contextmanager
def connection():
    conn=mysql.connector.connect(**db_config())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def query(sql,params=()):
    with connection() as conn:
        cur=conn.cursor(dictionary=True)
        cur.execute(sql,params)
        rows=cur.fetchall() if cur.with_rows else []
        cur.close()
        return rows

def execute(sql,params=()):
    with connection() as conn:
        cur=conn.cursor();cur.execute(sql,params);last=cur.lastrowid;cur.close();return last

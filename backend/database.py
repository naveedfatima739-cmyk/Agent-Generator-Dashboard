import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agents.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            dataset_path TEXT,
            embed_code TEXT,
            created_at TEXT NOT NULL,
            train_url TEXT
        )
    """)
    # Add train_url column to existing databases that were created before this fix
    try:
        c.execute("ALTER TABLE agents ADD COLUMN train_url TEXT")
        conn.commit()
    except Exception:
        pass  # Column already exists — safe to ignore
    conn.close()

def create_agent(agent_id: str, name: str, description: str = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO agents (id, name, description, created_at)
        VALUES (?, ?, ?, ?)
    """, (agent_id, name, description, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_agents():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM agents")
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "description": r[2], "dataset_path": r[3], "embed_code": r[4], "created_at": r[5], "train_url": r[6] if len(r) > 6 else None} for r in rows]

def get_agent(agent_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM agents WHERE id = ?", (agent_id,))
    r = c.fetchone()
    conn.close()
    if not r: return None
    return {"id": r[0], "name": r[1], "description": r[2], "dataset_path": r[3], "embed_code": r[4], "created_at": r[5], "train_url": r[6] if len(r) > 6 else None}

def update_agent(agent_id: str, **kwargs):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    sets = ", ".join([f"{k} = ?" for k in kwargs])
    vals = list(kwargs.values()) + [agent_id]
    c.execute(f"UPDATE agents SET {sets} WHERE id = ?", vals)
    conn.commit()
    conn.close()

def delete_agent(agent_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
    conn.commit()
    conn.close()
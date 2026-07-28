import sqlite3
from datetime import datetime
import os

DB_PATH = 'call_analyzer.db'

def init_db():
    """Bazani va jadvallarni yaratish"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Reports jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            chat_id INTEGER,
            chat_type TEXT,
            audio_type TEXT,
            report_text TEXT,
            created_at TIMESTAMP
        )
    ''')
    
    # Agar eski bazada score ustuni bo'lmasa, qo'shamiz
    try:
        cursor.execute("ALTER TABLE reports ADD COLUMN score INTEGER")
    except sqlite3.OperationalError:
        # Demak ustun allaqachon mavjud
        pass
        
    conn.commit()
    conn.close()

def save_report(user_id: int, username: str, chat_id: int, chat_type: str, audio_type: str, report_text: str, score: int = None):
    """Yangi tahlil natijasini bazaga saqlash"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO reports (user_id, username, chat_id, chat_type, audio_type, report_text, score, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, username, chat_id, chat_type, audio_type, report_text, score, datetime.now()))
    
    conn.commit()
    conn.close()

def get_stats():
    """Statistikani olish"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM reports')
    total_reports = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(DISTINCT user_id) FROM reports')
    unique_users = cursor.fetchone()[0]
    
    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute('SELECT COUNT(*) FROM reports WHERE date(created_at) = ?', (today,))
    today_reports = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        'total_reports': total_reports,
        'unique_users': unique_users,
        'today_reports': today_reports
    }

def get_top_employees(limit=10):
    """Eng yuqori ball to'plagan xodimlarni olish"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT username, AVG(score) as avg_score, COUNT(*) as report_count 
        FROM reports 
        WHERE score IS NOT NULL
        GROUP BY user_id, username
        ORDER BY avg_score DESC
        LIMIT ?
    ''', (limit,))
    
    results = cursor.fetchall()
    conn.close()
    
    return [{'username': r[0], 'avg_score': r[1], 'count': r[2]} for r in results]

def get_latest_reports(limit=5):
    """Oxirgi tahlillarni olish"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT username, score, created_at 
        FROM reports 
        ORDER BY created_at DESC 
        LIMIT ?
    ''', (limit,))
    
    results = cursor.fetchall()
    conn.close()
    
    return [{'username': r[0], 'score': r[1], 'created_at': r[2]} for r in results]

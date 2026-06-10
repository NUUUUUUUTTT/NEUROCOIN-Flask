from flask import Flask, request, jsonify, send_from_directory
import sqlite3
import os

app = Flask(__name__, static_folder='public')

DB_PATH = os.path.join(os.path.dirname(__file__), 'neurocoin.db')

# ── ПОДКЛЮЧЕНИЕ ───────────────────────────────────────────────
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def query(sql, params=(), one=False, commit=False):
    conn = get_conn()
    cur  = conn.execute(sql, params)
    if commit:
        conn.commit()
        result = cur.rowcount
    elif one:
        result = cur.fetchone()
    else:
        result = cur.fetchall()
    conn.close()
    return result

def query_returning(sql, params=()):
    conn = get_conn()
    cur  = conn.execute(sql, params)
    last_id = cur.lastrowid
    conn.commit()
    row = conn.execute("SELECT * FROM " + sql.split("INTO ")[1].split(" ")[0] + " WHERE id=?", (last_id,)).fetchone()
    conn.close()
    return dict(row)

# ── ИНИЦИАЛИЗАЦИЯ ─────────────────────────────────────────────
def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            login      TEXT NOT NULL UNIQUE,
            pass       TEXT NOT NULL,
            role       TEXT NOT NULL DEFAULT 'student',
            name       TEXT NOT NULL,
            group_name TEXT NOT NULL DEFAULT '',
            balance    INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS topics (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            lesson_date TEXT,
            price_3     INTEGER NOT NULL DEFAULT 30,
            price_4     INTEGER NOT NULL DEFAULT 60,
            price_5     INTEGER NOT NULL DEFAULT 90,
            price_z     INTEGER NOT NULL DEFAULT 120,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS requests (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            user_name   TEXT NOT NULL,
            user_group  TEXT NOT NULL DEFAULT '',
            topic_id    INTEGER NOT NULL REFERENCES topics(id) ON DELETE RESTRICT,
            topic_name  TEXT NOT NULL,
            grade       TEXT NOT NULL,
            price       INTEGER NOT NULL,
            status      TEXT NOT NULL DEFAULT 'pending',
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            desc_text  TEXT NOT NULL,
            amount     INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS teacher_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            student_name  TEXT NOT NULL,
            student_group TEXT NOT NULL DEFAULT '',
            amount        INTEGER NOT NULL,
            reason        TEXT NOT NULL DEFAULT '',
            created_at    TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS notifications (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            msg        TEXT NOT NULL,
            is_read    INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    # Учитель по умолчанию
    conn.execute("""
        INSERT OR IGNORE INTO users (login, pass, role, name, group_name)
        VALUES ('Teacher', 'TeacherSmotrit', 'teacher', 'Преподаватель', '')
    """)
    # Демо-темы
    count = conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0]
    if count == 0:
        conn.executemany(
            "INSERT INTO topics (name, price_3, price_4, price_5, price_z) VALUES (?,?,?,?,?)",
            [
                ('Введение в информационные системы', 30, 60, 90, 120),
                ('Основы программирования', 40, 75, 100, 130),
                ('Базы данных', 35, 65, 95, 125),
            ]
        )
    conn.commit()
    conn.close()
    print("✓ База данных готова (neurocoin.db)")

# ── HTML ──────────────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory('public', 'index.html')

# ══════════════════════════════════════════════════════════════
#  АВТОРИЗАЦИЯ
# ══════════════════════════════════════════════════════════════
@app.route('/api/login', methods=['POST'])
def login():
    d = request.json
    row = query("SELECT * FROM users WHERE login=? AND pass=?", (d['login'], d['pass']), one=True)
    if not row:
        return jsonify({'error': 'Неверный логин или пароль'}), 401
    return jsonify({'id': row['id'], 'login': row['login'], 'role': row['role'],
                    'name': row['name'], 'group': row['group_name'], 'balance': row['balance']})

@app.route('/api/register', methods=['POST'])
def register():
    d = request.json
    if not all([d.get('login'), d.get('pass'), d.get('name'), d.get('group')]):
        return jsonify({'error': 'Заполни все поля'}), 400
    if query("SELECT id FROM users WHERE login=?", (d['login'],), one=True):
        return jsonify({'error': 'Логин уже занят'}), 400
    row = query_returning(
        "INSERT INTO users (login, pass, role, name, group_name, balance) VALUES (?,?,'student',?,?,0)",
        (d['login'], d['pass'], d['name'], d['group'])
    )
    return jsonify({'id': row['id'], 'login': row['login'], 'role': 'student',
                    'name': row['name'], 'group': row['group_name'], 'balance': 0})

# ══════════════════════════════════════════════════════════════
#  ТЕМЫ
# ══════════════════════════════════════════════════════════════
@app.route('/api/topics', methods=['GET'])
def get_topics():
    rows = query("SELECT * FROM topics ORDER BY created_at")
    return jsonify([{'id': r['id'], 'name': r['name'], 'date': r['lesson_date'] or '',
                     'p3': r['price_3'], 'p4': r['price_4'], 'p5': r['price_5'], 'pz': r['price_z']} for r in rows])

@app.route('/api/topics', methods=['POST'])
def add_topic():
    d = request.json
    row = query_returning(
        "INSERT INTO topics (name, lesson_date, price_3, price_4, price_5, price_z) VALUES (?,?,?,?,?,?)",
        (d['name'], d.get('date') or None, d.get('p3',30), d.get('p4',60), d.get('p5',90), d.get('pz',120))
    )
    return jsonify({'id': row['id'], 'name': row['name'], 'date': row['lesson_date'] or '',
                    'p3': row['price_3'], 'p4': row['price_4'], 'p5': row['price_5'], 'pz': row['price_z']})

@app.route('/api/topics/<int:tid>', methods=['PATCH'])
def update_topic(tid):
    d = request.json
    query("UPDATE topics SET price_3=?, price_4=?, price_5=?, price_z=? WHERE id=?",
          (d['p3'], d['p4'], d['p5'], d['pz'], tid), commit=True)
    return jsonify({'ok': True})

@app.route('/api/topics/<int:tid>', methods=['DELETE'])
def delete_topic(tid):
    query("DELETE FROM topics WHERE id=?", (tid,), commit=True)
    return jsonify({'ok': True})

# ══════════════════════════════════════════════════════════════
#  ЗАПРОСЫ
# ══════════════════════════════════════════════════════════════
@app.route('/api/requests', methods=['GET'])
def get_requests():
    uid = request.args.get('userId')
    if uid:
        rows = query("SELECT * FROM requests WHERE user_id=? ORDER BY created_at DESC", (uid,))
    else:
        rows = query("SELECT * FROM requests ORDER BY created_at DESC")
    return jsonify([dict(r) for r in rows])

@app.route('/api/requests', methods=['POST'])
def add_request():
    d = request.json
    if query("SELECT id FROM requests WHERE user_id=? AND topic_id=? AND status IN ('pending','approved')",
             (d['userId'], d['topicId']), one=True):
        return jsonify({'error': 'Уже есть активный запрос по этой теме'}), 400
    row = query_returning(
        "INSERT INTO requests (user_id, user_name, user_group, topic_id, topic_name, grade, price) VALUES (?,?,?,?,?,?,?)",
        (d['userId'], d['userName'], d.get('userGroup',''), d['topicId'], d['topicName'], d['grade'], d['price'])
    )
    teacher = query("SELECT id FROM users WHERE role='teacher'", one=True)
    if teacher:
        query("INSERT INTO notifications (user_id, msg) VALUES (?,?)",
              (teacher['id'], f"📥 Запрос от {d['userName']} ({d.get('userGroup','')}): тема «{d['topicName']}», оценка {d['grade']}, стоимость {d['price']} NC"), commit=True)
    return jsonify(dict(row))

@app.route('/api/requests/<int:rid>/approve', methods=['POST'])
def approve_request(rid):
    req = query("SELECT * FROM requests WHERE id=? AND status='pending'", (rid,), one=True)
    if not req:
        return jsonify({'error': 'Запрос не найден'}), 404
    u = query("SELECT * FROM users WHERE id=?", (req['user_id'],), one=True)
    if u['balance'] < req['price']:
        return jsonify({'error': 'У студента недостаточно NC'}), 400
    new_bal = u['balance'] - req['price']
    conn = get_conn()
    try:
        conn.execute("UPDATE users SET balance=? WHERE id=?", (new_bal, u['id']))
        conn.execute("UPDATE requests SET status='approved' WHERE id=?", (rid,))
        conn.execute("INSERT INTO history (user_id, desc_text, amount) VALUES (?,?,?)",
                     (u['id'], f"Зачтено: {req['topic_name']} ({req['grade']})", -req['price']))
        conn.execute("INSERT INTO notifications (user_id, msg) VALUES (?,?)",
                     (u['id'], f"✓ Запрос одобрен: «{req['topic_name']}», оценка {req['grade']}. Списано {req['price']} NC. Остаток: {new_bal} NC"))
        conn.commit()
    except Exception as e:
        conn.rollback(); conn.close()
        return jsonify({'error': str(e)}), 500
    conn.close()
    return jsonify({'ok': True, 'newBalance': new_bal})

@app.route('/api/requests/<int:rid>/reject', methods=['POST'])
def reject_request(rid):
    req = query("SELECT * FROM requests WHERE id=? AND status='pending'", (rid,), one=True)
    if not req:
        return jsonify({'error': 'Запрос не найден'}), 404
    conn = get_conn()
    conn.execute("UPDATE requests SET status='rejected' WHERE id=?", (rid,))
    conn.execute("INSERT INTO notifications (user_id, msg) VALUES (?,?)",
                 (req['user_id'], f"✕ Запрос отклонён: «{req['topic_name']}», оценка {req['grade']}. NC не списаны."))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

# ══════════════════════════════════════════════════════════════
#  СТУДЕНТЫ
# ══════════════════════════════════════════════════════════════
@app.route('/api/students', methods=['GET'])
def get_students():
    rows = query("SELECT id, login, name, group_name, balance FROM users WHERE role='student' ORDER BY name")
    return jsonify([dict(r) for r in rows])

@app.route('/api/students', methods=['POST'])
def add_student():
    d = request.json
    if not all([d.get('login'), d.get('pass'), d.get('name'), d.get('group')]):
        return jsonify({'error': 'Заполни все поля'}), 400
    if query("SELECT id FROM users WHERE login=?", (d['login'],), one=True):
        return jsonify({'error': 'Логин уже занят'}), 400
    row = query_returning(
        "INSERT INTO users (login, pass, role, name, group_name, balance) VALUES (?,?,'student',?,?,?)",
        (d['login'], d['pass'], d['name'], d['group'], d.get('balance', 0))
    )
    return jsonify({'id': row['id'], 'login': row['login'], 'name': row['name'],
                    'group_name': row['group_name'], 'balance': row['balance']})

@app.route('/api/students/<int:uid>', methods=['DELETE'])
def delete_student(uid):
    query("DELETE FROM users WHERE id=? AND role='student'", (uid,), commit=True)
    return jsonify({'ok': True})

@app.route('/api/students/<int:uid>/coins', methods=['POST'])
def adjust_coins(uid):
    d = request.json
    amount = d['amount']
    reason = d.get('reason', '')
    u = query("SELECT * FROM users WHERE id=? AND role='student'", (uid,), one=True)
    if not u:
        return jsonify({'error': 'Студент не найден'}), 404
    new_bal = u['balance'] + amount
    if new_bal < 0:
        return jsonify({'error': 'Недостаточно NC у студента'}), 400
    conn = get_conn()
    try:
        conn.execute("UPDATE users SET balance=? WHERE id=?", (new_bal, uid))
        desc = ('Начислено' if amount > 0 else 'Списано') + ' преподавателем' + (f': {reason}' if reason else '')
        conn.execute("INSERT INTO history (user_id, desc_text, amount) VALUES (?,?,?)", (uid, desc, amount))
        conn.execute("INSERT INTO teacher_log (student_id, student_name, student_group, amount, reason) VALUES (?,?,?,?,?)",
             (u['id'], u['name'], u['group_name'], -req['price'], f"Зачтено: {req['topic_name']} ({req['grade']})"))
        msg = (f"⊕ Начислено {amount} NC" if amount > 0 else f"⊖ Списано {abs(amount)} NC") + \
              (f": {reason}" if reason else "") + f". Баланс: {new_bal} NC"
        conn.execute("INSERT INTO notifications (user_id, msg) VALUES (?,?)", (uid, msg))
        conn.commit()
    except Exception as e:
        conn.rollback(); conn.close()
        return jsonify({'error': str(e)}), 500
    conn.close()
    return jsonify({'ok': True, 'newBalance': new_bal})

# ══════════════════════════════════════════════════════════════
#  ИСТОРИЯ / ЛОГ / УВЕДОМЛЕНИЯ
# ══════════════════════════════════════════════════════════════
@app.route('/api/history/<int:uid>', methods=['GET'])
def get_history(uid):
    rows = query("SELECT * FROM history WHERE user_id=? ORDER BY created_at DESC", (uid,))
    return jsonify([dict(r) for r in rows])

@app.route('/api/teacher/all-history', methods=['GET'])
def get_all_history():
    rows = query("""
        SELECT h.*, u.name as student_name, u.group_name as student_group
        FROM history h
        JOIN users u ON u.id = h.user_id
        ORDER BY h.created_at DESC
    """)
    return jsonify([dict(r) for r in rows])

@app.route('/api/teacher-log', methods=['GET'])
def get_teacher_log():
    rows = query("SELECT * FROM teacher_log ORDER BY created_at DESC LIMIT 200")
    return jsonify([dict(r) for r in rows])

@app.route('/api/notifications/<int:uid>', methods=['GET'])
def get_notifications(uid):
    rows = query("SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 50", (uid,))
    return jsonify([dict(r) for r in rows])

@app.route('/api/notifications/<int:uid>/read-all', methods=['POST'])
def read_all(uid):
    query("UPDATE notifications SET is_read=1 WHERE user_id=?", (uid,), commit=True)
    return jsonify({'ok': True})

@app.route('/api/balance/<int:uid>', methods=['GET'])
def get_balance(uid):
    row = query("SELECT balance FROM users WHERE id=?", (uid,), one=True)
    return jsonify({'balance': row['balance'] if row else 0})

# ══════════════════════════════════════════════════════════════
#  ЗАПУСК
# ══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    init_db()
    print("\n  Открой в браузере: http://localhost:5000\n")
    app.run(debug=True, port=5000)

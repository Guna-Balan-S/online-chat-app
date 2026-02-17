import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request, redirect, session
from flask_socketio import SocketIO, join_room, leave_room, emit
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

app = Flask(__name__)
app.config['SECRET_KEY'] = 'super-secret-key'

socketio = SocketIO(app, cors_allowed_origins="*")

DATABASE = 'users_new.db'


users = {}          # username -> socket id
user_rooms = {}     # username -> current room


# ------------------ DATABASE ------------------

def init_db():
    conn = sqlite3.connect(DATABASE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)
    conn.close()

init_db()


# ------------------ ROUTES ------------------

@app.route('/')
def index():
    if 'username' in session:
        return render_template('chat.html', username=session['username'])
    return redirect('/login')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect(DATABASE)
        user = conn.execute(
            "SELECT * FROM users WHERE username=?",
            (username,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            session['username'] = username
            return redirect('/')

        return render_template('login.html',
                               error="Invalid username or password")

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])

        conn = sqlite3.connect(DATABASE)
        try:
            conn.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, password)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return render_template('register.html',
                                   error="User already exists")
        conn.close()
        return redirect('/login')

    return render_template('register.html')


# ------------------ SOCKET EVENTS ------------------

@socketio.on('connect')
def handle_connect():
    print("Connected:", request.sid)


@socketio.on('disconnect')
def handle_disconnect():
    for username, sid in list(users.items()):
        if sid == request.sid:
            users.pop(username)
            user_rooms.pop(username, None)
            break


# 🔵 JOIN ROOM
@socketio.on('join_room_event')
def handle_join(data):
    username = data['username']
    room = data['room']

    users[username] = request.sid

    # Leave previous room if exists
    if username in user_rooms:
        leave_room(user_rooms[username])

    join_room(room)
    user_rooms[username] = room

    emit("room_joined", {"room": room}, to=request.sid)


# 🔵 ROOM MESSAGE
@socketio.on('room_message')
def handle_room_message(data):
    emit(
        "room_message",
        {
            "from": data["from"],
            "msg": data["msg"],
            "room": data["room"]
        },
        to=data["room"]
    )


# 🔵 PRIVATE MESSAGE
@socketio.on('private_message')
def handle_private(data):
    sender = data['from']
    recipient = data['to']
    message = data['msg']

    if recipient in users:
        emit(
            "private_message",
            {
                "from": sender,
                "to": recipient,
                "msg": message
            },
            to=users[recipient]
        )

    # send back to sender
    emit(
        "private_message",
        {
            "from": sender,
            "to": recipient,
            "msg": message
        },
        to=request.sid
    )


# ------------------ RUN ------------------

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)

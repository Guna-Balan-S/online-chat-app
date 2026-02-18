import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request, redirect, session
from flask_socketio import SocketIO, join_room, leave_room, emit
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
import os

# ------------------ APP CONFIG ------------------

app = Flask(__name__)
app.config['SECRET_KEY'] = 'super-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# Use environment variable from Render
DATABASE_URL = os.environ.get("DATABASE_URL")

users = {}          # username -> socket id
user_rooms = {}     # username -> current room

# ------------------ DATABASE ------------------

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)


def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(150) UNIQUE NOT NULL,
            password TEXT NOT NULL
        );
    """)
    conn.commit()
    cur.close()
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

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT password FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user and check_password_hash(user[0], password):
            session['username'] = username
            return redirect('/')

        return render_template('login.html', error="Invalid username or password")

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])

        conn = get_db_connection()
        cur = conn.cursor()

        try:
            cur.execute(
                "INSERT INTO users (username, password) VALUES (%s, %s)",
                (username, password)
            )
            conn.commit()
        except psycopg2.Error:
            conn.rollback()
            cur.close()
            conn.close()
            return render_template('register.html', error="User already exists")

        cur.close()
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


@socketio.on('join_room_event')
def handle_join(data):
    username = data['username']
    room = data['room']

    users[username] = request.sid

    if username in user_rooms:
        leave_room(user_rooms[username])

    join_room(room)
    user_rooms[username] = room

    emit("room_joined", {"room": room}, to=request.sid)


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

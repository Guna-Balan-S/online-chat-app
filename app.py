import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request, redirect, session
from flask_socketio import SocketIO, send, join_room, leave_room, emit
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

# ------------------ APP CONFIG ------------------

app = Flask(__name__)
app.config['SECRET_KEY'] = 'super-secret-key'

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="eventlet",
    transports=["polling"]
)

DATABASE = 'users_fresh.db'

users = {}          # username -> socket id
rooms = set(["main"])  # default room

# ------------------ DATABASE ------------------

def init_db():
    conn = sqlite3.connect(DATABASE)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    conn.close()

init_db()

# ------------------ ROUTES ------------------

@app.route('/')
def index():
    if 'username' in session:
        return render_template('chat.html', username=session['username'])
    return redirect('/login')


@app.route('/users')
def get_users():
    conn = sqlite3.connect(DATABASE)
    users_list = conn.execute(
        'SELECT username FROM users'
    ).fetchall()
    conn.close()

    return {'users': [u[0] for u in users_list]}


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect(DATABASE)
        user = conn.execute(
            'SELECT * FROM users WHERE username=?',
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
        password = request.form['password']

        hashed_password = generate_password_hash(password)

        conn = sqlite3.connect(DATABASE)
        try:
            conn.execute(
                'INSERT INTO users (username, password) VALUES (?, ?)',
                (username, hashed_password)
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

# 🔵 CONNECT / DISCONNECT

@socketio.on('connect')
def handle_connect():
    print("User connected:", request.sid)


@socketio.on('disconnect')
def handle_disconnect():
    for username, sid in list(users.items()):
        if sid == request.sid:
            del users[username]
            break


# 🔵 JOIN DEFAULT ROOM

@socketio.on('join')
def handle_join(data):
    username = data['username']
    room = data['room']
    users[username] = request.sid
    join_room(room)
    send(f"{username} joined the room.", to=room)

# 🔵 CREATE ROOM

@socketio.on('create_room')
def handle_create_room(data):
    room = data['room']
    rooms.add(room)

    emit('room_created',
         {'room': room},
         broadcast=True)


# 🔵 JOIN ROOM

@socketio.on('join_room_event')
def handle_join_room(data):
    username = data['username']
    room = data['room']

    users[username] = request.sid
    join_room(room)

    send(f"{username} joined {room}", to=room)


# 🔵 ROOM MESSAGE

@socketio.on('room_message')
def handle_room_message(data):
    emit(
        'room_message',
        {
            'from': data['from'],
            'msg': data['msg'],
            'room': data['room']
        },
        to=data['room']
    )


# 🔵 PRIVATE MESSAGE

@socketio.on('private_message')
def handle_private(data):
    sender = data['from']
    recipient = data['to']
    message = data['msg']

    if recipient in users:
        emit(
            'private_message',
            {
                'from': sender,
                'msg': message
            },
            to=users[recipient]
        )

    # send back to sender
    emit(
        'private_message',
        {
            'from': sender,
            'msg': message
        },
        to=request.sid
    )


# 🔵 TYPING INDICATOR

@socketio.on('typing')
def handle_typing(data):
    emit('typing', data, to=data['room'], include_self=False)


@socketio.on('stop_typing')
def handle_stop_typing(data):
    emit('stop_typing', data, to=data['room'], include_self=False)


# ------------------ RUN ------------------

if __name__ == "__main__":
    socketio.run(app)

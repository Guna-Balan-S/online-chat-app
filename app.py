import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request, redirect, session
from flask_socketio import SocketIO, send, join_room, emit
import sqlite3

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="eventlet",
    transports=["polling"]
)


users = {}

# ------------------ DATABASE ------------------

def init_db():
    conn = sqlite3.connect('users.db')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE,
            password TEXT
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


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect('users.db')
        user = conn.execute(
            'SELECT * FROM users WHERE username=? AND password=?',
            (username, password)
        ).fetchone()
        conn.close()

        if user:
            session['username'] = username
            return redirect('/')
        return "Invalid credentials"

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect('users.db')
        try:
            conn.execute(
                'INSERT INTO users (username, password) VALUES (?, ?)',
                (username, password)
            )
            conn.commit()
        except:
            return "User already exists"
        finally:
            conn.close()

        return redirect('/login')

    return render_template('register.html')

# ------------------ SOCKET EVENTS ------------------

@socketio.on('join')
def handle_join(data):
    username = data['username']
    room = data['room']

    users[username] = request.sid
    join_room(room)
    send(f"{username} joined the room.", to=room)


@socketio.on('message')
def handle_message(data):
    send(data['msg'], to=data['room'])


@socketio.on('private_message')
def handle_private(data):
    recipient = data['to']
    message = data['msg']
    sender = data['from']

    if recipient in users:
        emit('private_message',
             f"(Private) {sender}: {message}",
             to=users[recipient])

    # ALSO send back to sender
    emit('private_message',
         f"(Private) You: {message}",
         to=request.sid)

@socketio.on('connect')
def handle_connect():
    print("User connected:", request.sid)


# ------------------ RUN ------------------

if __name__ == "__main__":
    socketio.run(app)



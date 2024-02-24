from socket import SocketIO
from flask import Flask, jsonify, request
import sqlite3
import threading

from src.proxy import DB_NAME


API_PORT = 8000
APP_NAME = 'proxy'


app = Flask(APP_NAME)
# socketio = SocketIO(app, 'r')



@app.route('/requests', methods=['GET'])
def get_requests():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM requests')
    requests = cursor.fetchall()
    conn.close()
    return jsonify(requests)


@app.route('/requests/<int:request_id>', methods=['GET'])
def get_request(request_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM requests WHERE id = ?', (request_id,))
    request_data = cursor.fetchone()
    conn.close()
    return jsonify(request_data)


@app.route('/repeat/<int:request_id>', methods=['GET'])
def repeat_request(request_id):
    # Здесь должна быть логика повторной отправки запроса
    pass


@app.route('/scan/<int:request_id>', methods=['GET'])
def scan_request(request_id):
    # Здесь должна быть логика сканирования запроса
    pass


def run_api_server(port: int = API_PORT):
    # socketio.run(app)
    app.run(port=port, debug=True)
    # print(f'api is running on port {port}')


if __name__ == '__main__':
    api_thread = threading.Thread(target=run_api_server)
    api_thread.start()

from flask import Flask, jsonify, g
import sqlite3

import config
from src.proxy import ProxyRequestHandler, Request


DELAY_ON_EXCEPTION = 0.5
MAX_ATTEMPTS = 5


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(config.DB)
    return g.db


app = Flask(config.APP_NAME)


@app.route('/requests', methods=['GET'])
def get_requests():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM request')
    requests = cursor.fetchall()
    return jsonify(requests)


@app.route('/requests/<int:request_id>', methods=['GET'])
def get_request(request_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM request WHERE id = ?', (request_id,))
    request_data = cursor.fetchone()
    return jsonify(request_data)


@app.route('/responses', methods=['GET'])
def get_responses():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM response')
    requests = cursor.fetchall()
    return jsonify(requests)


@app.route('/responses/<int:response_id>', methods=['GET'])
def get_response(response_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM response WHERE id = ?', (response_id,))
    request_data = cursor.fetchone()
    return jsonify(request_data)


@app.route('/repeat/<int:request_id>', methods=['GET'])
def repeat_request(request_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM request WHERE id = ?', (request_id,))
    request_data = cursor.fetchone()
    if request_data is None:
        return jsonify({"error": "Request not found"}), 404

    request = Request.from_db(request_data[1:])
    response = ProxyRequestHandler.send_request_get_response(request)
    return jsonify(response.to_dict())


@app.route('/scan/<int:request_id>', methods=['GET'])
def scan_request(request_id):
    # Здесь должна быть логика сканирования запроса
    pass


def run_api_server(port: int = config.API_PORT):
    app.run(port=port, debug=True)


if __name__ == '__main__':
    run_api_server()

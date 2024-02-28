from flask import Flask, jsonify, g
import sqlite3

import config
from src.response import Response
from src.proxy import ProxyRequestHandler
from src.request import Request


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
    requests_rows = cursor.fetchall()
    result = []
    for request_row in requests_rows:
        result.append(Request.from_db(request_row).to_dict())
    return jsonify(result)


@app.route('/requests/<int:request_id>', methods=['GET'])
def get_request(request_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM request WHERE id = ?', (request_id,))
    request_row = cursor.fetchone()
    return jsonify(Request.from_db(request_row).to_dict())


@app.route('/responses', methods=['GET'])
def get_responses():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM response')
    responses = cursor.fetchall()
    result = []
    for response in responses:
        result.append(Response.from_db(response).to_dict())

    return jsonify(result)


@app.route('/responses/<int:response_id>', methods=['GET'])
def get_response(response_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM response WHERE id = ?', (response_id,))
    response_data = cursor.fetchone()
    return jsonify(Response.from_db(response_data).to_dict())


@app.route('/repeat/<int:request_id>', methods=['GET'])
def repeat_request(request_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM request WHERE id = ?', (request_id,))
    request_data = cursor.fetchone()
    if request_data is None:
        return jsonify({"error": "Request not found"}), 404

    is_https = request_data[10]
    request = Request.from_db(request_data)
    response = ProxyRequestHandler.send_request_get_response(request, is_https)
    try:
        return jsonify(response.to_dict())
    except UnicodeDecodeError:
        return jsonify({'error': 'unsupported content encoding'}), 501


@app.route('/scan/<int:request_id>', methods=['GET'])
def scan_request(request_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM request WHERE id = ?', (request_id,))
    request_data = cursor.fetchone()
    if request_data is None:
        return jsonify({"error": "Request not found"}), 404

    is_https = request_data[10]
    original_request = Request.from_db(request_data)
    original_response = ProxyRequestHandler.send_request_get_response(
        original_request,
        is_https,
    )

    vulnerabilities = []
    for modified_request in original_request:
        modified_response = ProxyRequestHandler.send_request_get_response(
            modified_request,
            is_https,
        )
        if modified_response != original_response:
            vulnerabilities.append({
                'param': modified_request.injection_points[
                    original_request.current_injection_index - 1
                ][0],
                'type': 'SQL Injection'
            })

    return jsonify({'vulnerabilities': vulnerabilities})


def run_api_server(port: int = config.API_PORT):
    app.run(host='0.0.0.0', port=port, debug=True)


if __name__ == '__main__':
    run_api_server()

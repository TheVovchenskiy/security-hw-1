import copy
import http
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
from http.client import HTTPConnection, HTTPResponse, InvalidURL
import json
import select
import socket
from socketserver import BaseRequestHandler, ThreadingMixIn
import sqlite3
import ssl
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

import httptools

from src.cert_utils import generate_host_certificate
import config

BUFSIZE = 4096

NEW_LINE = '\r\n'
COLON = ':'
DOUBLE_SLAH = '//'
DOUBLE_QUOTES = '"'
SINGLE_QUOTES = "'"


class Request:
    def __init__(
        self,
        request_handler: BaseHTTPRequestHandler = None,
        **kwargs,
    ) -> None:
        if request_handler:
            self.request_handler = request_handler
            self._parse_request()
        elif 'raw' in kwargs:
            self._parse_raw(kwargs['raw'])
        else:
            self.method = kwargs.get('method')
            self.host = kwargs.get('host')
            self.port = kwargs.get('port', 80)
            self.path = kwargs.get('path')
            self.get_params = kwargs.get('get_params', {})
            self.headers = kwargs.get('headers', {})
            self.cookies = kwargs.get('cookies', SimpleCookie())
            self.body = kwargs.get('body')
            self.post_params = kwargs.get('post_params', {})

    @classmethod
    def from_db(cls, db_row):
        method, host, port, path, get_params, headers, cookies, body, post_params = db_row[1:]
        return cls(
            method=method,
            host=host,
            port=port,
            path=path,
            get_params=json.loads(get_params),
            headers=json.loads(headers),
            cookies=SimpleCookie(json.loads(cookies)),
            body=body,
            post_params=json.loads(post_params)
        )

    @classmethod
    def from_raw_request(cls, raw_request: bytes):
        return cls(raw=raw_request)

    def _parse_raw(self, raw_request):
        self.headers = {}
        self.body = None
        p = httptools.HttpRequestParser(self)
        p.feed_data(raw_request)

        self.method = p.get_method()
        self.host, self.port = self._parse_host_port(
            self.headers.get('Host', None),
        )
        self._parse_get_params()
        self._parse_post_params()
        self._parse_cookies()

    def on_header(self, name: bytes, value: bytes):
        self.headers[name.decode()] = value.decode()

    def on_body(self, body: bytes):
        if self.body is None:
            self.body = b''
        self.body += body

    def on_url(self, url: bytes):
        self.path = url.decode()

    def _parse_request(self):
        self._parse_headers()
        self._parse_body()
        try:
            self._parse_path()
            self.host, self.port = self._parse_host_port(
                self.headers.get('Host', None),
            )
        except ValueError:
            err = http.HTTPStatus.BAD_REQUEST
            self.send_error(
                err.value,
                f"Invalid url '{self.request_handler.path}'",
                err.description,
            )
            return
        self._parse_cookies()
        self._parse_method()
        self._parse_get_params()
        self._parse_post_params()

    def _parse_path(self) -> None:
        url = urlparse(self.request_handler.path)
        self.path = url.path if url.path else '/'

    @staticmethod
    def _parse_host_port(host_header_value: str) -> tuple[str, int]:
        if host_header_value is None:
            raise ValueError("no header 'Host' in request headers")

        host_header_value = host_header_value.split(COLON, 1)
        if len(host_header_value) == 2:
            return host_header_value[0], int(host_header_value[-1])

        elif len(host_header_value) == 1:
            return host_header_value[0], 80

        else:
            raise ValueError("invalid header 'Host' in request headers")

    def _parse_body(self) -> None:
        content_length = self.request_handler.headers['Content-Length']
        if content_length:
            content_length = int(content_length)
            self.body = self.request_handler.rfile.read(content_length)
        else:
            self.body = None

    def _parse_headers(self) -> None:
        self.headers = {
            header_name: header_value
            for header_name, header_value in self.request_handler.headers.items()
            if header_name not in ['Proxy-Connection']
        }

    def _parse_cookies(self) -> None:
        self.cookies = SimpleCookie()
        self.cookies.load(self.headers.get('Cookie', ''))

    def _parse_method(self):
        self.method = self.request_handler.command

    def _parse_get_params(self) -> None:
        self.get_params = parse_qs(urlparse(self.path).query)
        self.get_params = {
            k: v[0] if len(v) == 1 else v
            for k, v in self.get_params.items()
        }

    def _parse_post_params(self) -> None:
        content_type = self.headers.get('Content-Type', '')
        self.post_params = parse_qs(self.body.decode()) \
            if 'application/x-www-form-urlencoded' in content_type else {}

    def save_to_db(
        self,
        db_conn: sqlite3.Connection,
        db_cursor: sqlite3.Cursor,
    ) -> int:
        db_cursor.execute('''
            INSERT INTO request (method, host, port, path, get_params, headers, cookies, body, post_params)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            self.method,
            self.host,
            self.port,
            self.path,
            json.dumps(self.get_params),
            json.dumps(self.headers),
            json.dumps({k: v.value for k, v in self.cookies.items()}),
            self.body,
            json.dumps(self.post_params)
        ))
        db_conn.commit()
        return db_cursor.lastrowid

    def __iter__(self):
        self._injection_points = self._get_injection_points()
        self._current_injection_index = 0
        return self

    def __next__(self):
        if self._current_injection_index >= len(self._injection_points):
            raise StopIteration

        injection_point = self._injection_points[self._current_injection_index]
        self._current_injection_index += 1

        modified_request = copy.deepcopy(self)
        key, value = injection_point
        if key in modified_request.get_params:
            modified_request.get_params[key] = value
        elif key in modified_request.post_params:
            modified_request.post_params[key] = value
        elif key in modified_request.headers:
            modified_request.headers[key] = value
        elif key == 'Cookie':
            modified_request.cookies.load(value)
            if key in modified_request.headers:
                modified_request.headers[key] = modified_request.cookies.output(
                    header="Cookie:")

        return modified_request

    def _get_injection_points(self):
        injection_points = []
        for key in self.get_params:
            injection_points.append(
                (key, self.get_params[key] + SINGLE_QUOTES))
            injection_points.append(
                (key, self.get_params[key] + DOUBLE_QUOTES))

        for key in self.post_params:
            injection_points.append(
                (key, self.post_params[key] + SINGLE_QUOTES))
            injection_points.append(
                (key, self.post_params[key] + DOUBLE_QUOTES))

        for key in self.headers:
            if key == 'Cookie':
                continue
            injection_points.append((key, self.headers[key] + SINGLE_QUOTES))
            injection_points.append((key, self.headers[key] + DOUBLE_QUOTES))

        if self.cookies:
            for key in self.cookies:
                injection_points.append(
                    ('Cookie', f"{key}={self.cookies[key].value}'"))
                injection_points.append(
                    ('Cookie', f"{key}={self.cookies[key].value}\""))

        return injection_points


class Response:
    def __init__(
        self,
        response: HTTPResponse = None,
        **kwargs
    ) -> None:
        if response:
            self.code = response.status
            self.message = response.reason
            self.headers = dict(response.getheaders())
            self.body = response.read().decode()
        elif 'raw' in kwargs:
            self._parse_raw(kwargs['raw'])
        else:
            self.code = kwargs.code
            self.message = kwargs.message
            self.headers = kwargs.headers
            self.body = kwargs.body

    @classmethod
    def from_db(cls, db_row):
        code, message, headers, body = db_row[2:]
        return cls(
            code=code,
            message=message,
            headers=headers,
            body=body,
        )

    @classmethod
    def from_raw_response(cls, raw_request: bytes):
        return cls(raw=raw_request)

    def _parse_raw(self, raw_response: bytes):
        self.headers = {}
        self.body = b''
        p = httptools.HttpResponseParser(self)
        p.feed_data(raw_response)

        self.code = p.get_status_code()
        self.message = http.HTTPStatus(self.code).phrase

    def on_header(self, name: bytes, value: bytes):
        self.headers[name.decode()] = value.decode()

    def on_body(self, body: bytes):
        if self.body is None:
            self.body = b''
        self.body += body

    def save_to_db(
        self,
        request_id: int,
        db_conn: sqlite3.Connection,
        db_cursor: sqlite3.Cursor,
    ):
        db_cursor.execute('''
            INSERT INTO response (request_id, code, message, headers, body)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            request_id,
            self.code,
            self.message,
            json.dumps(self.headers),
            self.body,
        ))
        db_conn.commit()

    def to_dict(self) -> dict:
        return {
            'code': self.code,
            'message': self.message,
            'headers': self.headers,
            'body': self.body,
        }


class ThreadingProxy(ThreadingMixIn, HTTPServer):
    def __init__(
            self,
            server_address: tuple[str | bytes | bytearray, int],
            RequestHandlerClass: Callable[[Any, Any, Any], BaseRequestHandler],
            db_conn,
            db_cursor,
            bind_and_activate: bool = True,
    ) -> None:
        self.db_conn = db_conn
        self.db_cursor = db_cursor
        super().__init__(
            server_address,
            RequestHandlerClass,
            bind_and_activate,
        )

    def finish_request(self, request, client_address):
        self.RequestHandlerClass(
            request,
            client_address,
            self,
            self.db_cursor,
            self.db_conn,
        )


class ProxyRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, request, client_address, server, db_cursor, db_conn):
        self.db_cursor = db_cursor
        self.db_conn = db_conn
        super().__init__(request, client_address, server)

    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()

    def do_HEAD(self):
        self.handle_request()

    def do_OPTIONS(self):
        self.handle_request()

    def do_CONNECT(self):
        self.handle_connect_request()
        self.close_connection = True

    def handle_connect_request(self):
        host, port = self.path.split(COLON)
        port = int(port)

        cert_path, key_path = generate_host_certificate(host)

        try:
            target_context = ssl.create_default_context()
            target_conn = target_context.wrap_socket(
                socket.create_connection((host, port)),
                server_hostname=host,
            )
        except socket.error:
            err = http.HTTPStatus.BAD_GATEWAY
            self.send_error(
                err.value,
                f"Cannot connect to '{host}:{port}'",
                err.description,
            )
            return

        self.send_response(200, 'Connection established')
        self.end_headers()

        try:
            client_context = ssl.create_default_context(
                ssl.Purpose.CLIENT_AUTH)
            client_context.load_cert_chain(
                certfile=cert_path, keyfile=key_path)
            client_conn = client_context.wrap_socket(
                self.connection,
                server_side=True,
            )
        except Exception as e:
            target_conn.close()
            raise RuntimeError(
                'something went wrong while wrapping client connection'
            ) from e

        self._forward_data(client_conn, target_conn)

    def _forward_data(
        self,
        client_conn: ssl.SSLSocket,
        target_conn: ssl.SSLSocket,
    ):
        inputs = [client_conn, target_conn]
        keep_running = True

        raw_request = b''
        raw_response = b''

        while keep_running:
            readable, _, exceptional = select.select(inputs, [], inputs, 10)
            if exceptional:
                break

            for s in readable:
                other = target_conn if s is client_conn else client_conn
                try:
                    data = s.recv(BUFSIZE)
                    if data:
                        if s is client_conn:
                            raw_request += data
                        elif s is target_conn:
                            raw_response += data
                        other.sendall(data)
                    else:
                        keep_running = False
                        break
                except socket.error as e:
                    keep_running = False
                    break

        request = Request.from_raw_request(raw_request)
        request_id = request.save_to_db(self.db_conn, self.db_cursor)

        response = Response.from_raw_response(raw_response)
        response.save_to_db(request_id, self.db_conn, self.db_cursor)

        client_conn.close()
        target_conn.close()

    def handle_request(self):
        try:
            request = Request(self)
        except ValueError:
            err = http.HTTPStatus.BAD_REQUEST
            self.send_error(
                err.value,
                f"Invalid request",
                err.description,
            )
            return
        request_id = request.save_to_db(self.db_conn, self.db_cursor)

        try:
            response = self.send_request_get_response(request)
        except InvalidURL:
            err = http.HTTPStatus.BAD_REQUEST
            self.send_error(
                err.value,
                f"Invalid url: '{self.path}'",
                err.description,
            )
            return
        except socket.error:
            err = http.HTTPStatus.BAD_REQUEST
            self.send_error(
                err.value,
                f"Could not send request to host",
                err.description,
            )
            return
        except Exception as e:
            err = http.HTTPStatus.BAD_GATEWAY
            self.send_error(
                err.value,
                f"Cannot connect to '{request.host}:{request.port}'",
                err.description,
            )
            return

        self._transmit_response(response, request_id)

    @staticmethod
    def send_request_get_response(request: Request) -> Response:
        conn = HTTPConnection(request.host, request.port)
        conn.request(
            request.method,
            request.path,
            body=request.body,
            headers=request.headers,
        )
        response = Response(conn.getresponse())
        conn.close()
        return response

    def _transmit_response(self, response: Response, request_id: int):
        self.send_response(response.code, response.message)
        for header, value in response.headers.items():
            self.send_header(header, value)
        self.end_headers()

        self.wfile.write(response.body.encode())
        response.save_to_db(request_id, self.db_conn, self.db_cursor)


class ProxyServer:
    def __init__(self, port=config.PROXY_PORT) -> None:
        self.port = port
        self.init_db()
        self.proxy_server = ThreadingProxy(
            ('', port),
            ProxyRequestHandler,
            self.db_conn,
            self.db_cursor,
        )

    def init_db(self):
        self.db_conn = sqlite3.connect(config.DB, check_same_thread=False)
        self.db_cursor = self.db_conn.cursor()
        self.db_cursor.execute('''
            CREATE TABLE IF NOT EXISTS request (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                method TEXT,
                host TEXT,
                port INTEGER,
                path TEXT,
                get_params TEXT,
                headers TEXT,
                cookies TEXT,
                body TEXT,
                post_params TEXT
            )
        ''')
        self.db_cursor.execute('''
            CREATE TABLE IF NOT EXISTS response (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER,
                code INTEGER,
                message TEXT,
                headers TEXT,
                body TEXT,
                FOREIGN KEY(request_id) REFERENCES requests(id)
            )
        ''')
        self.db_conn.commit()

    def run(self):
        print(f'proxy server is running on port {self.port}')
        try:
            self.proxy_server.serve_forever()
        except KeyboardInterrupt:
            print(f'{NEW_LINE}proxy server is stopped')
        except Exception as e:
            print(f'unexpected error occured: {e}')
        finally:
            self.db_cursor.close()
            self.db_conn.close()

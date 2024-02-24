import http
from http.server import BaseHTTPRequestHandler, HTTPServer
from http.client import HTTPConnection, HTTPSConnection, InvalidURL
import json
import os
import select
import socket
from socketserver import BaseRequestHandler, ThreadingMixIn
import sqlite3
import ssl
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse, ParseResult

from src.cert_utils import generate_host_certificate
import config

BUFSIZE = 4096

NEW_LINE = '\r\n'
COLON = ':'
DOUBLE_SLAH = '//'


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

        while keep_running:
            readable, _, exceptional = select.select(inputs, [], inputs, 10)
            if exceptional:
                break

            for s in readable:
                other = target_conn if s is client_conn else client_conn
                try:
                    data = s.recv(BUFSIZE)
                    if data:
                        other.sendall(data)
                    else:
                        keep_running = False
                        break
                except socket.error as e:
                    keep_running = False
                    break

        client_conn.close()
        target_conn.close()

    def handle_request(self):
        try:
            host, path, port = self._parse_url()
        except ValueError:
            err = http.HTTPStatus.BAD_REQUEST
            self.send_error(
                err.value,
                f"Invalid url '{self.path}'",
                err.description,
            )
            return

        body = self._get_request_body()
        headers = self._filter_headers()

        parsed_request = {
            "method": self.command,
            "path": self.path,
            "get_params": self._parse_get_params(),
            "headers": headers,
            "cookies": self._parse_cookies(),
            "post_params": self._parse_post_params(body)
        }
        request_id = self._save_request_to_db(parsed_request)

        try:
            conn = HTTPConnection(host, port)
        except InvalidURL:
            err = http.HTTPStatus.BAD_REQUEST
            self.send_error(
                err.value,
                f"Invalid url: '{self.path}'",
                err.description,
            )
        except Exception as e:
            err = http.HTTPStatus.BAD_GATEWAY
            self.send_error(
                err.value,
                f"Cannot connect to '{host}:{port}'",
                err.description,
            )

        conn.request(
            self.command,
            path,
            body=body,
            headers=headers,
        )

        response = conn.getresponse()
        self._transmit_response(response, request_id)

        conn.close()

    def _filter_headers(self):
        return {
            header_name: header_value
            for header_name, header_value in self.headers.items()
            if header_name != 'Proxy-Connection'
        }

    def _parse_url(self) -> tuple[str, str, int]:
        url = urlparse(self.path)
        host = self._get_host(url)
        path = self._get_relative_path(url)
        port = self._get_port(url)

        return host, path, port

    def _get_host(self, url: ParseResult) -> str:
        host: str | None = self.headers['Host']
        if host is None:
            raise ValueError("no header 'Host' in request headers")
        url_host = url.hostname
        if url_host and host != url_host:
            raise ValueError("host in headers and in url do not match")

        return host

    def _get_relative_path(self, url: ParseResult) -> str:
        return url.path if url.path else '/'

    def _get_port(self, url: ParseResult) -> int:
        return url.port if url.port else 80

    def _get_request_body(self) -> bytes | None:
        content_length = self.headers['Content-Length']
        if content_length:
            content_length = int(content_length)
            body = self.rfile.read(content_length)
        else:
            body = None

        return body

    def _transmit_response(self, response, request_id):
        self.send_response(response.status, response.reason)
        for header, value in response.getheaders():
            self.send_header(header, value)
        self.end_headers()

        data = response.read()
        self.wfile.write(data)

        parsed_response = {
            "code": response.status,
            "message": response.reason,
            "headers": self._parse_response_headers(response),
            "body": data.decode()
        }
        self._save_response_to_db(parsed_response, request_id)

    def _parse_get_params(self):
        get_params = parse_qs(urlparse(self.path).query)
        get_params = {k: v[0] if len(
            v) == 1 else v for k, v in get_params.items()}
        return get_params

    def _parse_cookies(self):
        cookies = self.headers.get('Cookie', '')
        return dict(x.split('=') for x in cookies.split('; ') if x)

    def _parse_post_params(self, body):
        content_type = self.headers.get('Content-Type', '')
        if 'application/x-www-form-urlencoded' in content_type:
            return parse_qs(body.decode())
        return {}

    def _parse_response_headers(self, response):
        return dict(response.getheaders())

    def _save_request_to_db(self, parsed_request):
        self.db_cursor.execute('''
            INSERT INTO requests (method, path, get_params, headers, cookies, post_params)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            parsed_request['method'],
            parsed_request['path'],
            json.dumps(parsed_request['get_params']),
            json.dumps(parsed_request['headers']),
            json.dumps(parsed_request['cookies']),
            json.dumps(parsed_request['post_params'])
        ))
        self.db_conn.commit()
        return self.db_cursor.lastrowid

    def _save_response_to_db(self, parsed_response, request_id):
        self.db_cursor.execute('''
            INSERT INTO responses (request_id, code, message, headers, body)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            request_id,
            parsed_response['code'],
            parsed_response['message'],
            json.dumps(parsed_response['headers']),
            parsed_response['body']
        ))
        self.db_conn.commit()


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
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                method TEXT,
                path TEXT,
                get_params TEXT,
                headers TEXT,
                cookies TEXT,
                post_params TEXT
            )
        ''')
        self.db_cursor.execute('''
            CREATE TABLE IF NOT EXISTS responses (
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

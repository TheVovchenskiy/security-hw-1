from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from http.client import HTTPConnection, HTTPSConnection, InvalidURL
import select
import socket
from socketserver import BaseRequestHandler, ThreadingMixIn
import sqlite3
import ssl
from typing import Any, Callable


from src.response import Response
from src.request import Request
from src.consts import COLON, NEW_LINE
from src.cert_utils import generate_host_certificate
import config

BUFSIZE = 4096


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
            err = HTTPStatus.BAD_GATEWAY
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
                except socket.error:
                    keep_running = False
                    break

        request = Request.from_raw_request(raw_request)
        request_id = request.save_to_db(self.db_conn, self.db_cursor, True)

        response = Response.from_raw_response(raw_response)
        response.save_to_db(request_id, self.db_conn, self.db_cursor)

        client_conn.close()
        target_conn.close()

    def handle_request(self):
        try:
            request = Request(self)
        except ValueError:
            err = HTTPStatus.BAD_REQUEST
            self.send_error(
                err.value,
                "Invalid request",
                err.description,
            )
            return
        request_id = request.save_to_db(self.db_conn, self.db_cursor)

        try:
            response = self.send_request_get_response(request)
        except InvalidURL:
            err = HTTPStatus.BAD_REQUEST
            self.send_error(
                err.value,
                f"Invalid url: '{self.path}'",
                err.description,
            )
            return
        except socket.error:
            err = HTTPStatus.BAD_REQUEST
            self.send_error(
                err.value,
                "Could not send request to host",
                err.description,
            )
            return
        except Exception:
            err = HTTPStatus.BAD_GATEWAY
            self.send_error(
                err.value,
                f"Cannot connect to '{request.host}:{request.port}'",
                err.description,
            )
            return

        self._transmit_response(response, request_id)

    @staticmethod
    def send_request_get_response(
        request: Request,
        is_https=False,
    ) -> Response:
        if is_https:
            conn = HTTPSConnection(request.host)
        else:
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
                post_params TEXT,
                is_https BOOLEAN
            )
        ''')
        self.db_cursor.execute('''
            CREATE TABLE IF NOT EXISTS response (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER,
                code INTEGER,
                message TEXT,
                headers TEXT,
                set_cookie TEXT,
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

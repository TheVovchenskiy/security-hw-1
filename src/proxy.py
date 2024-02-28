from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from http.client import HTTPConnection, HTTPSConnection, InvalidURL
import os
import select
import socket
from socketserver import BaseRequestHandler, ThreadingMixIn
import sqlite3
import ssl
from threading import Lock
from typing import Any, Callable

import httptools


from src.response import Response
from src.request import Request
from src.consts import COLON, NEW_LINE
from src.cert_utils import CERTS_DIR, SERIAL_NUMBERS_DIR, generate_host_certificate
import config

BUFSIZE = 4096


lock = Lock()


class ThreadingProxy(ThreadingMixIn, HTTPServer):
    def __init__(
            self,
            server_address: tuple[str | bytes | bytearray, int],
            RequestHandlerClass: Callable[[Any, Any, Any], BaseRequestHandler],
            db_conn,
            bind_and_activate: bool = True,
    ) -> None:
        self.db_conn = db_conn
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
            self.db_conn,
        )


class ProxyRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, request, client_address, server, db_conn):
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

        try:
            cert_path, key_path = generate_host_certificate(host)
        except Exception as e:
            # print('error:', e)
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR)
            raise e

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
            print(
                'something went wrong while wrapping client connection: ',
                e
            )
        else:
            try:
                self._forward_data(client_conn, target_conn)
            except EOFError:
                pass

        try:
            os.remove(cert_path)
        except FileNotFoundError:
            pass

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
            readable, _, exceptional = select.select(inputs, [], inputs, 1)
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

        if raw_request != b'':
            try:
                request = Request.from_raw_request(raw_request)
                with lock:
                    request_id = request.save_to_db(self.db_conn, True)
            except ValueError:
                print('invalid http request headers')
            except httptools.parser.errors.HttpParserUpgrade:
                print('cannot save request to db')
            except AttributeError:
                print('cannot save request to db')
            else:
                try:
                    response = Response.from_raw_response(raw_response)
                    with lock:
                        response.save_to_db(request_id, self.db_conn)
                except ValueError:
                    pass

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

        with lock:
            request_id = request.save_to_db(self.db_conn)

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

        self.wfile.write(response.body)
        with lock:
            response.save_to_db(request_id, self.db_conn)


class ProxyServer:
    def __init__(self, port=config.PROXY_PORT) -> None:
        self.port = port
        self.init_db()
        self.proxy_server = ThreadingProxy(
            ('', port),
            ProxyRequestHandler,
            self.db_conn,
        )

    def init_db(self):
        self.db_conn = sqlite3.connect(config.DB, check_same_thread=False)
        db_cursor = self.db_conn.cursor()
        db_cursor.execute('''
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
        db_cursor.execute('''
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
            self.db_conn.close()
            for _, _, files in os.walk(CERTS_DIR):
                for file in files:
                    os.remove(os.path.join(CERTS_DIR, file))

            for _, _, files in os.walk(SERIAL_NUMBERS_DIR):
                for file in files:
                    os.remove(os.path.join(SERIAL_NUMBERS_DIR, file))

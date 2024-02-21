import http
from http.server import BaseHTTPRequestHandler, HTTPServer
import socket
from socketserver import ThreadingMixIn
from urllib.parse import urlparse


PORT = 8080
BUFSIZE = 4096
NEW_LINE = '\r\n'


class ThreadingProxy(ThreadingMixIn, HTTPServer):
    pass


class HttpProxyRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()

    def do_HEAD(self):
        self.handle_request()

    def do_OPTIONS(self):
        self.handle_request()

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

        if host is None:
            host = self.headers['Host']

        request = self._modify_request(path)

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as conn:
            try:
                conn.connect((host, port))
            except socket.gaierror:
                err = http.HTTPStatus.BAD_GATEWAY
                self.send_error(
                    err.value,
                    f"Cannot connect to '{host}:{port}'",
                    err.description,
                )
            else:
                self._send_request(conn, request)
                self._transmit_response(conn)

    def _parse_url(self) -> tuple[str | None, str, int]:
        url = urlparse(self.path)
        host = url.hostname
        path = url.path if url.path else '/'
        port = url.port if url.port else 80

        return host, path, port

    def _modify_request(self, path: str) -> str:
        request_line = f'{self.command} {path} {self.protocol_version}'

        del self.headers['Proxy-Connection']
        request_headers = NEW_LINE.join(
            f'{header_name}: {header_value}'
            for header_name, header_value in self.headers.items()
        )
        return request_line + NEW_LINE + request_headers + NEW_LINE

    def _send_request(self, conn: socket.socket, request: str):
        conn.sendall(request.encode())

    def _transmit_response(self, conn: socket.socket):
        response = conn.recv(BUFSIZE)
        while response:
            self.wfile.write(response)
            response = conn.recv(BUFSIZE)


class HttpProxyServer:
    def __init__(self, port=PORT) -> None:
        self.port = port
        self.proxy_server = ThreadingProxy(('', port), HttpProxyRequestHandler)

    def run(self):
        print(f'proxy server is running on port {self.port}')
        try:
            self.proxy_server.serve_forever()
        except KeyboardInterrupt:
            print(f'{NEW_LINE}proxy server is stopped')
        except Exception as e:
            print(f'unexpected error occured: {e}')

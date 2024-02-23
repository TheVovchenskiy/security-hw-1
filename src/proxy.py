import http
from http.server import BaseHTTPRequestHandler, HTTPServer
from http.client import HTTPConnection, HTTPSConnection, InvalidURL
import select
import socket
from socketserver import ThreadingMixIn
import ssl
from urllib.parse import urlparse, ParseResult

from src.cert_utils import generate_host_certificate


PORT = 8080
BUFSIZE = 4096

NEW_LINE = '\r\n'
COLON = ':'
DOUBLE_SLAH = '//'


class ThreadingProxy(ThreadingMixIn, HTTPServer):
    pass


class ProxyRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

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
        headers = {
            header_name: header_value
            for header_name, header_value in self.headers.items()
            if header_name != 'Proxy-Connection'
        }

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
        self._transmit_response(response)

        conn.close()

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

    def _transmit_response(self, response):
        self.send_response(response.status, response.reason)
        for header, value in response.getheaders():
            self.send_header(header, value)
        self.end_headers()

        self.wfile.write(response.read())


class ProxyServer:
    def __init__(self, port=PORT) -> None:
        self.port = port
        self.proxy_server = ThreadingProxy(('', port), ProxyRequestHandler)

    def run(self):
        print(f'proxy server is running on port {self.port}')
        try:
            self.proxy_server.serve_forever()
        except KeyboardInterrupt:
            print(f'{NEW_LINE}proxy server is stopped')
        except Exception as e:
            print(f'unexpected error occured: {e}')

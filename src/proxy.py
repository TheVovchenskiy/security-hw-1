import http
from http.server import BaseHTTPRequestHandler, HTTPServer
from http.client import HTTPConnection, InvalidURL
# import socket
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, ParseResult


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
        host = self.headers['Host']
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

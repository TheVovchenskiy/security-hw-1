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
    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()

    def do_HEAD(self):
        self.handle_request()

    def do_OPTIONS(self):
        self.handle_request()

    def handle_request(self):
        url = urlparse(self.path)

        host = url.hostname
        path = url.path if url.path else '/'
        port = url.port if url.port else 80

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as conn:
            conn.connect((host, port))

            del self.headers['Proxy-Connection']
            request_line = f'{self.command} {path} {self.protocol_version}'
            request_headers = NEW_LINE.join(
                f'{k}: {v}'
                for k, v in self.headers.items()
            )
            request = NEW_LINE.join([
                request_line,
                request_headers,
            ]) + NEW_LINE * 2

            conn.sendall(request.encode())

            self._transmit_response(conn)

    def _transmit_response(self, conn: socket.socket):
        response = conn.recv(BUFSIZE)
        while response:
            self.wfile.write(response)
            response = conn.recv(BUFSIZE)


def run_proxy(port=PORT):
    proxy_server = ThreadingProxy(('', port), HttpProxyRequestHandler)
    print(f'proxy server is running on port {port}')
    proxy_server.serve_forever()


if __name__ == '__main__':
    run_proxy()

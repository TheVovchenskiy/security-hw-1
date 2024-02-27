import copy
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
import json
import sqlite3
from urllib.parse import parse_qs, urlparse

import httptools

from src.consts import COLON, DOUBLE_QUOTES, SINGLE_QUOTES


COOKIE_HEADER = 'Cookie'

DEFAULT_PORT = {
    'http': 80,
    'https': 443,
}


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
        (
            method,
            host,
            port,
            path,
            get_params,
            headers,
            cookies,
            body,
            post_params,
        ) = db_row[
            1:10]
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

        self.method = p.get_method().decode()
        self._parse_get_params()
        self._parse_post_params()
        self._parse_cookies()
        self._parse_host_port_path(self.path)

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
        self._parse_cookies()
        self._parse_method()
        self._parse_get_params()
        self._parse_post_params()
        try:
            self._parse_host_port_path(self.request_handler.path)
        except ValueError as e:
            raise ValueError from e

    def _parse_path(self) -> None:
        url = urlparse(self.request_handler.path)
        self.path = url.path if url.path else '/'

    @staticmethod
    def parse_host_port(netloc: str) -> tuple[str, int]:
        host_port = netloc.split(COLON, 1)
        if len(host_port) == 2:
            return host_port[0], int(host_port[-1])

        if len(host_port) == 1:
            return host_port[0], 80

    def _parse_host_port_path(self, uri: str):
        if self.method == 'CONNECT':
            self.host, self.port = self.parse_host_port(uri)
        elif self.method == 'OPTIONS':
            pass
        else:
            parsed_url = urlparse(uri)
            if parsed_url.scheme:
                self.host = parsed_url.hostname
                self.port = parsed_url.port \
                    if parsed_url.port \
                    else 80
                self.headers['Host'] = parsed_url.netloc
                self.path = parsed_url.path
            elif self.headers['Host']:
                self.host, self.port = self.parse_host_port(
                    self.headers['Host'],
                )
                self.path = parsed_url.path
            else:
                raise ValueError("invalid request")

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
            for header_name, header_value
            in self.request_handler.headers.items()
            if header_name not in ['Proxy-Connection']
        }

    def _parse_cookies(self) -> None:
        self.cookies = SimpleCookie()
        self.cookies.load(self.headers.get(COOKIE_HEADER, ''))

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
        is_https=False,
    ) -> int:
        db_cursor = db_conn.cursor()
        db_cursor.execute('''
            INSERT INTO request (method, host, port, path, get_params, headers, cookies, body, post_params, is_https)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            self.method,
            self.host,
            self.port,
            self.path,
            json.dumps(self.get_params),
            json.dumps(self.headers),
            json.dumps({k: v.value for k, v in self.cookies.items()}),
            self.body,
            json.dumps(self.post_params),
            is_https,
        ))
        db_conn.commit()
        return db_cursor.lastrowid

    def __iter__(self):
        self.injection_points = self._get_injection_points()
        self.current_injection_index = 0
        return self

    def __next__(self):
        if self.current_injection_index >= len(self.injection_points):
            raise StopIteration

        injection_point = self.injection_points[self.current_injection_index]
        self.current_injection_index += 1

        modified_request = copy.deepcopy(self)
        key, value = injection_point
        if key in modified_request.get_params:
            modified_request.get_params[key] = value

        elif key in modified_request.post_params:
            modified_request.post_params[key] = value

        elif key in modified_request.headers:
            modified_request.headers[key] = value

        elif key == COOKIE_HEADER:
            modified_request.cookies.load(value)
            if key in modified_request.headers:
                modified_request.headers[key] = modified_request.cookies.output(
                    header=f'{COOKIE_HEADER}:'
                )

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
            if key == COOKIE_HEADER:
                continue
            injection_points.append((key, self.headers[key] + SINGLE_QUOTES))
            injection_points.append((key, self.headers[key] + DOUBLE_QUOTES))

        if self.cookies:
            for key in self.cookies:
                injection_points.append(
                    (COOKIE_HEADER, f"{key}={self.cookies[key].value}'"))
                injection_points.append(
                    (COOKIE_HEADER, f"{key}={self.cookies[key].value}\""))

        return injection_points

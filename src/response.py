import gzip
from http import HTTPStatus
from http.client import HTTPResponse
from http.cookies import SimpleCookie
import json
import sqlite3

import httptools

from src.consts import NEW_LINE


COOKIE_HEADER = 'Set-Cookie'


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
            self.body = response.read()

            self._parse_cookies()
        elif 'raw' in kwargs:
            self._parse_raw(kwargs['raw'])
        else:
            self.code = kwargs['code']
            self.message = kwargs['message']
            self.headers = kwargs['headers']
            self.set_cookie = kwargs.get('set_cookie', SimpleCookie())
            self.body = kwargs['body']
        
        try:
            self._handle_content_encoding()
        except gzip.BadGzipFile:
            pass

    def _handle_content_encoding(self):
        if 'Content-Encoding' in self.headers:
            self.body = gzip.decompress(self.body)

    @classmethod
    def from_db(cls, db_row):
        code, message, headers, set_cookie, body = db_row[2:]
        return cls(
            code=code,
            message=message,
            headers=headers,
            set_cookie=SimpleCookie(json.loads(set_cookie)),
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
        try:
            self.message = HTTPStatus(self.code).phrase
        except ValueError as e:
            raise e

        self._parse_cookies()

    def on_header(self, name: bytes, value: bytes):
        self.headers[name.decode()] = value.decode()

    def on_body(self, body: bytes):
        if self.body is None:
            self.body = b''
        self.body += body

    def _parse_cookies(self):
        self.set_cookie = SimpleCookie()
        self.set_cookie.load(self.headers.get(COOKIE_HEADER, ''))

    def save_to_db(
        self,
        request_id: int,
        db_conn: sqlite3.Connection,
    ):
        db_cursor = db_conn.cursor()
        db_cursor.execute('''
            INSERT INTO response (request_id, code, message, headers, set_cookie, body)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            request_id,
            self.code,
            self.message,
            json.dumps(self.headers),
            json.dumps(self.set_cookie),
            self.body,
        ))
        db_conn.commit()

    def to_dict(self) -> dict:
        try:
            body = self.body.decode()
        except UnicodeDecodeError:
            body = 'unsupported content encoding'
        return {
            'code': self.code,
            'message': self.message,
            'headers': self.headers,
            'set_cookies': dict(self.set_cookie),
            'body': body,
        }

    def __eq__(self, __value: object) -> bool:
        return (
            self.code == __value.code and
            len(self.body) == len(__value.body)
        )

    def __str__(self) -> str:
        return NEW_LINE.join([
            f'{self.code}',
            *[
                f'{header}: {field_value}'
                for header, field_value in self.headers.items()
            ],
            '',
            self.body.decode()[:10] + '...' if self.body else '',
        ])

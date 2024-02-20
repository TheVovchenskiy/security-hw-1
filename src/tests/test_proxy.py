from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from src.proxy import HttpProxyRequestHandler


class SocketConnectionMock:
    def connect(self, addr):
        pass

    def sendall(data: bytes):
        pass

    def recv(bufsize: int) -> bytes:
        return 'response'.encode()


class MakeFileMock:
    def __init__(self, raw_requestline: bytes) -> None:
        self.raw_requestline = raw_requestline

    def readline(self, *args, **kwargs) -> bytes:
        return self.raw_requestline

    def close(self):
        pass


class RequestMock:
    def __init__(self, url: str, raw_requestline: bytes) -> None:
        self.raw_requestline = raw_requestline

    def makefile(self, *args, **kwargs):
        return MakeFileMock(self.raw_requestline)

    def sendall(self, b):
        pass


@dataclass
class ParseUrlData:
    url: str
    expected_host: str
    expected_path: str
    expected_port: int


def test_parse_correct_url():
    test_data = [
        ParseUrlData('http://example.com/test', 'example.com', '/test', 80),
        ParseUrlData('http://example.com:8194/test',
                     'example.com', '/test', 8194),
        ParseUrlData('http://example.com:80/test', 'example.com', '/test', 80),
        ParseUrlData('http://example.com/', 'example.com', '/', 80),
        ParseUrlData('http://example.com', 'example.com', '/', 80),
        # ParseUrlData('//example.com/test', 'example.com', '/test', 80),
        # ParseUrlData('example.com/test', 'example.com', '/test', 80),
        ParseUrlData('http://example.com/test?x=254&b=sdfd',
                     'example.com', '/test', 80),
        ParseUrlData('http://example.com:8040/test?x=254&b=sdfd',
                     'example.com', '/test', 8040),
    ]

    for test_case in test_data:
        request_mock = RequestMock(
            url=test_case.url,
            raw_requestline=f'GET {test_case.url} HTTP/1.1\r\n'.encode(),
        )
        # request_mock.makefile = MagicMock()
        handler = HttpProxyRequestHandler(
            request_mock,
            MagicMock(),
            MagicMock(),
        )
        # handler.path = test_case.url
        actual_host, actual_path, actual_port = handler._parse_url()
        assert actual_host == test_case.expected_host
        assert actual_path == test_case.expected_path
        assert actual_port == test_case.expected_port


def test_parse_invalid_url():
    test_data = [
        'http://example.com:dfsd/test',
        'http://ex:ample.com/test',
        'http://example.com:65536/test',
    ]

    for url in test_data:
        print(url)
        request_mock = RequestMock(
            url=url,
            raw_requestline=f'GET {url} HTTP/1.1\r\n'.encode(),
        )
        # request_mock.makefile = MagicMock()
        handler = HttpProxyRequestHandler(
            request_mock,
            MagicMock(),
            MagicMock(),
        )

        with pytest.raises(ValueError):
            handler._parse_url()

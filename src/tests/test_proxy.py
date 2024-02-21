from dataclasses import dataclass
from http import HTTPStatus
import socket
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.proxy import HttpProxyRequestHandler, NEW_LINE


class SocketConnectionMock:
    def connect(self, addr):
        pass

    def sendall(data: bytes):
        pass

    def recv(bufsize: int) -> bytes:
        return 'response'.encode()


class FileMock:
    def __init__(self, str_data: str) -> None:
        self.data = str_data.split(NEW_LINE)
        self.curr_line_idx = 0

    def readline(self, *args, **kwargs) -> bytes:
        if self.curr_line_idx < len(self.data):
            result = self.data[self.curr_line_idx] + NEW_LINE
            self.curr_line_idx += 1
            return result.encode()
        return b''

    def write(self, *args):
        pass

    def close(self):
        pass


class RequestMock:
    def __init__(self, data: str) -> None:
        self.data = data

    def makefile(self, *args, **kwargs):
        return FileMock(self.data)

    def sendall(self, b):
        pass


class SocketMock:
    def __init__(
            self,
            received_data: str,
            connect_err: Exception = None,
    ) -> None:
        self.received_data = received_data
        self.curr_left_border = 0
        self.connect_err = connect_err

    def __call__(self, *args: Any, **kwds: Any) -> Any:
        return self

    def __enter__(self, *args, **kwargs):
        return self

    def __exit__(self, *args):
        pass

    def connect(self, *args):
        if self.connect_err:
            raise self.connect_err

    def sendall(self, *args) -> str:
        pass

    def recv(self, bufsize: int):
        if self.curr_left_border + bufsize < len(self.received_data):
            return self.received_data[self.curr_left_border:self.curr_left_border+bufsize]
        elif self.curr_left_border < len(self.received_data):
            return self.received_data[self.curr_left_border:]
        else:
            return None


@dataclass
class ParseUrlData:
    url: str
    expected_host: str
    expected_path: str
    expected_port: int


@patch.object(HttpProxyRequestHandler, 'handle_request')
def test_parse_correct_url(mock_handle_request):
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
        # print(test_case.url)
        request_mock = RequestMock(
            data=f'GET {test_case.url} HTTP/1.1' + NEW_LINE
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


@patch.object(HttpProxyRequestHandler, 'handle_request')
def test_parse_invalid_url(mock_handle_request):
    test_data = [
        'http://example.com:dfsd/test',
        'http://ex:ample.com/test',
        'http://example.com:65536/test',
    ]

    for url in test_data:
        print(url)
        request_mock = RequestMock(
            data=f'GET {url} HTTP/1.1' + NEW_LINE,
        )
        # request_mock.makefile = MagicMock()
        handler = HttpProxyRequestHandler(
            request_mock,
            MagicMock(),
            MagicMock(),
        )

        with pytest.raises(ValueError):
            handler._parse_url()


@dataclass
class ModifyRequestData:
    request: str
    expected: str


@patch.object(HttpProxyRequestHandler, 'handle_request')
def test_modify_request(mock_handle_request):
    data = [
        ModifyRequestData(
            NEW_LINE.join([
                'GET http://example.com/test HTTP/1.1',
                'Host: example.com',
                'User-Agent: curl/7.64.1',
                'Accept: */*',
                'Proxy-Connection: Keep-Alive',
                '',
            ]),
            NEW_LINE.join([
                'GET /test HTTP/1.1',
                'Host: example.com',
                'User-Agent: curl/7.64.1',
                'Accept: */*',
                '',
            ]),
        ),
        ModifyRequestData(
            NEW_LINE.join([
                'GET http://example.com/test HTTP/1.1',
                'Host: example.com',
                'User-Agent: curl/7.64.1',
                'Accept: */*',
                '',
            ]),
            NEW_LINE.join([
                'GET /test HTTP/1.1',
                'Host: example.com',
                'User-Agent: curl/7.64.1',
                'Accept: */*',
                '',
            ]),
        )
    ]

    for test_case in data:
        request_mock = RequestMock(data=test_case.request)
        handler = HttpProxyRequestHandler(
            request_mock,
            MagicMock(),
            MagicMock(),
        )

        actual = handler._modify_request('/test')
        assert actual == test_case.expected


def test_socket(mocker):
    request_mock = RequestMock(
        data='GET http://example.com/test HTTP/1.1' + NEW_LINE
    )
    socket_mock = mocker.patch(
        'src.proxy.socket.socket',
        return_value=SocketMock(''),
    )
    HttpProxyRequestHandler(
        request_mock,
        MagicMock(),
        MagicMock(),
    )

    expected_calls = [
        mocker.call(socket.AF_INET, socket.SOCK_STREAM)
    ]
    assert socket_mock.mock_calls == expected_calls


def test_socket_exception(mocker):
    request_mock = RequestMock(
        data='GET http://example.com/test HTTP/1.1' + NEW_LINE
    )
    socket_mock = mocker.patch(
        'src.proxy.socket.socket',
        return_value=SocketMock('', connect_err=socket.gaierror),
    )
    with patch.object(HttpProxyRequestHandler, 'send_error') as send_error_mock:
        handler = HttpProxyRequestHandler(
            request_mock,
            MagicMock(),
            MagicMock(),
        )

    send_error_mock.assert_called_once_with(
        HTTPStatus.BAD_GATEWAY.value,
        "Cannot connect to 'example.com:80'",
        HTTPStatus.BAD_GATEWAY.description,
    )


@patch.object(HttpProxyRequestHandler, '_parse_url', side_effect=ValueError)
def test_handle_request_value_error(mock):
    request_mock = RequestMock(
        data='GET http://example.com/test HTTP/1.1' + NEW_LINE
    )

    with patch.object(HttpProxyRequestHandler, 'send_error') as send_error_mock:
        handler = HttpProxyRequestHandler(
            request_mock,
            MagicMock(),
            MagicMock(),
        )

    send_error_mock.assert_called_once_with(
        HTTPStatus.BAD_REQUEST.value,
        "Invalid url 'http://example.com/test'",
        HTTPStatus.BAD_REQUEST.description,
    )


@patch.object(HttpProxyRequestHandler, 'do_GET')
def test_get_method(get_mock):
    request_mock = RequestMock(
        data='GET http://example.com/test HTTP/1.1' + NEW_LINE
    )

    HttpProxyRequestHandler(
        request_mock,
        MagicMock(),
        MagicMock(),
    )

    get_mock.assert_called_once()


@patch.object(HttpProxyRequestHandler, 'do_POST')
def test_post_method(post_mock):
    request_mock = RequestMock(
        data='POST http://example.com/test HTTP/1.1' + NEW_LINE
    )

    HttpProxyRequestHandler(
        request_mock,
        MagicMock(),
        MagicMock(),
    )

    post_mock.assert_called_once()


@patch.object(HttpProxyRequestHandler, 'do_HEAD')
def test_head_method(head_mock):
    request_mock = RequestMock(
        data='HEAD http://example.com/test HTTP/1.1' + NEW_LINE
    )

    HttpProxyRequestHandler(
        request_mock,
        MagicMock(),
        MagicMock(),
    )

    head_mock.assert_called_once()


@patch.object(HttpProxyRequestHandler, 'do_OPTIONS')
def test_options_method(options_mock):
    request_mock = RequestMock(
        data='OPTIONS http://example.com/test HTTP/1.1' + NEW_LINE
    )

    HttpProxyRequestHandler(
        request_mock,
        MagicMock(),
        MagicMock(),
    )

    options_mock.assert_called_once()

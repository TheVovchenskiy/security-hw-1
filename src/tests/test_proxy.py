from dataclasses import dataclass
from http import HTTPStatus
import io
from unittest.mock import MagicMock, patch

import pytest

from src.proxy import HttpProxyRequestHandler, NEW_LINE


class RequestMock:
    def __init__(self, data: str) -> None:
        self.data = data

    def makefile(self, *args, **kwargs):
        return io.BytesIO(self.data.encode())

    def sendall(self, b):
        pass


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
        ParseUrlData('http://example.com/test?x=254&b=sdfd',
                     'example.com', '/test', 80),
        ParseUrlData('http://example.com:8040/test?x=254&b=sdfd',
                     'example.com', '/test', 8040),
    ]

    for test_case in test_data:
        request_mock = RequestMock(
            data=f'GET {test_case.url} HTTP/1.1' + NEW_LINE +
            'Host: example.com' + NEW_LINE
        )
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
class GetRequestBodyData:
    request_lines: list[str]
    expected: str | None


# @patch.object(HttpProxyRequestHandler, 'handle_request')
# def test_get_request_body(mock):
#     data = [
#         GetRequestBodyData(
#             request_lines=[
#                 'GET http://example.com/test HTTP/1.1',
#                 'Host: example.com',
#                 'Content-Length: 2',
#                 '',
#                 'df',
#                 '',
#             ],
#             expected='df'
#         ),
#         GetRequestBodyData(
#             request_lines=[
#                 'GET http://example.com/test HTTP/1.1',
#                 'Host: example.com',
#                 '',
#             ],
#             expected=None
#         ),
#     ]

#     for test_case in data:
#         request_mock = RequestMock(
#             data=NEW_LINE.join(test_case.request_lines),
#         )
#         handler = HttpProxyRequestHandler(
#             request_mock,
#             MagicMock(),
#             MagicMock(),
#         )

#         actual = handler._get_request_body()
#         assert actual.decode() == test_case.expected


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

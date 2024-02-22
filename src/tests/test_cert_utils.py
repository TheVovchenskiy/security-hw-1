from dataclasses import dataclass
from unittest.mock import patch

from src.cert_utils import get_next_serial_number


class FileMock:
    def __init__(self, init_number: int | None = None) -> None:
        if init_number is None:
            self.data: str | None = None
        else:
            self.data: str | None = str(init_number)

    def __enter__(self, *args, **kwargs):
        return self

    def __exit__(self, *args, **kwargs):
        pass

    def read(self) -> str:
        if self.data is None:
            return ''
        return self.data

    def write(self, data: str):
        self.data = data


def test_get_next_serial_number_file_exists(mocker):
    os_exists_mock = mocker.patch(
        'src.cert_utils.os.path.exists',
        return_value=True,
    )
    host = 'host'
    for i in range(100):
        open_mock = mocker.patch(
            'src.cert_utils.open',
            return_value=FileMock(i)
        )
        actual = get_next_serial_number(host)
        assert actual == i + 1


def test_get_next_serial_number_file_not_exists(mocker):
    os_exists_mock = mocker.patch(
        'src.cert_utils.os.path.exists',
        return_value=False,
    )
    host = 'host'
    open_mock = mocker.patch(
        'src.cert_utils.open',
        return_value=FileMock()
    )
    actual1 = get_next_serial_number(host)
    assert actual1 == 1

    os_exists_mock = mocker.patch(
        'src.cert_utils.os.path.exists',
        return_value=True,
    )
    actual2 = get_next_serial_number(host)
    assert actual2 == 2

    actual3 = get_next_serial_number(host)
    assert actual3 == 3

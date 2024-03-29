import os
import subprocess
from threading import Lock


CERTS_DIR = 'certs'
CA_CERT = 'ca.crt'
CERT_KEY = 'cert.key'
CA_KEY = 'ca.key'
SERIAL_NUMBERS_DIR = 'serial_numbers'


# lock = Lock()


if not all(map(os.path.exists, [CA_CERT, CA_KEY, CERTS_DIR])):
    raise FileNotFoundError(
        f"files '{CA_CERT}', '{CA_KEY}' or directory '{CERTS_DIR}' "
        "are not found"
    )


def generate_host_certificate(host: str):
    try:
        serial = get_next_serial_number(host)
    except ValueError:
        print(f'{host=}')

    host_cert_name = f"{host}_{serial}.crt"
    host_csr_name = f"{host}_{serial}.csr"

    cert_path = os.path.join(CERTS_DIR, host_cert_name)

    csr_path = os.path.join(CERTS_DIR, host_csr_name)
    subprocess.run(
        [
            "openssl", "req", "-new", "-key", CERT_KEY, "-out", csr_path,
            "-subj", f"/CN={host}"
        ],
        check=True,
        capture_output=True,
    )

    subprocess.run(
        [
            "openssl", "x509", "-req", "-days", "3650", "-in", csr_path,
            "-CA", CA_CERT, "-CAkey", CA_KEY, "-set_serial", str(serial),
            "-out", cert_path
        ],
        check=True,
        capture_output=True,
    )

    try:
        os.remove(csr_path)
    except FileNotFoundError:
        pass

    return cert_path, CERT_KEY


def get_next_serial_number(host: str) -> int:
    serial_number_file = os.path.join(
        SERIAL_NUMBERS_DIR,
        f'{host}_serial_number.txt',
    )
    if not os.path.exists(serial_number_file):
        with open(serial_number_file, 'w') as f:
            f.write('0')

    with open(serial_number_file, 'r') as f:
        serial = int(f.read().strip())

    serial += 1

    with open(serial_number_file, 'w') as f:
        f.write(str(serial))

    return serial

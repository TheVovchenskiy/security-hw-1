import os
import subprocess


CERTS_DIR = 'certs'
CA_CERT = 'ca.crt'
CA_KEY = 'ca.key'
SERIAL_NUMBERS_DIR = 'serial_numbers'


if not all(map(os.path.exists, [CA_CERT, CA_KEY, CERTS_DIR])):
    raise FileNotFoundError(
        f"files '{CA_CERT}', '{CA_KEY}' or directory '{CERTS_DIR}' "
        "are not found"
    )


def generate_host_certificate(host: str):
    host_cert_name = f"{host}.crt"
    host_key_name = f"{host}.key"
    host_csr_name = f"{host}.csr"

    cert_path = os.path.join(CERTS_DIR, host_cert_name)
    key_path = os.path.join(CERTS_DIR, host_key_name)
    if not os.path.exists(cert_path) or not os.path.exists(key_path):
        subprocess.run(["openssl", "genrsa", "-out",
                       key_path, "2048"], check=True)

        csr_path = os.path.join(CERTS_DIR, host_csr_name)
        subprocess.run([
            "openssl", "req", "-new", "-key", key_path, "-out", csr_path,
            "-subj", f"/CN={host}"
        ], check=True)

        serial = get_next_serial_number(host)
        subprocess.run([
            "openssl", "x509", "-req", "-days", "3650", "-in", csr_path,
            "-CA", CA_CERT, "-CAkey", CA_KEY, "-set_serial", str(serial),
            "-out", cert_path
        ], check=True)

        os.remove(csr_path)

    return cert_path, key_path


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

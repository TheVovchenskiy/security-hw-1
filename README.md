# Simple proxy server

## Creating sertificates

To make it easier to setup proxy server I created `Makefile`.

To start using this server run following shell command:

```bash
make create-cert
```

This will create all necessery root certificates and keys.

On **Linux** copy file `ca.crt` to `/usr/local/share/ca-certificates` in order to add this certificate as trusted. Use following comand

```bash
make add-trusted-cert
```

<span style='color: red'><b>WARNING</b><br>if you are using other platforms please add this certificate to trusted store according to your platform instruction</span>

## Docker

To build and run docker containers run following command:

```bash
make docker-compose-up
```

Now proxy server is running on `8080` port and api server is running on `8000` port.

## API

Allowed endpoints:

- `GET /requests`
- `GET /requests/<request_id>`
- `GET /responses`
- `GET /responses/<response_id>`
- `GET /repeat/<request_id>`
- `GET /scan/<request_id>`

## Data base

After running the containers, `sqlite3` database created in `db/` directory.

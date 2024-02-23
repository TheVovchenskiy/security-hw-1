# Simple proxy server

## Creating sertificates

To make it easier to setup proxy server I created `Makefile`.

To start using this server run following shell command:

```bash
make cert
```

This will create all necessery root certificates and keys.

On Linus copy file `ca.crt` to `/usr/local/share/ca-certificates` in order to add this certificate as trusted. Use following comand
```bash
make add-trusted-cert
```

## Docker

To build and run docker container run following commands:
```bash
make docker-build
make docker-run
```
Now proxy server is running on 8080 port.

.PHONY: create-cert
create-cert:
	openssl genrsa -out ca.key 2048
	openssl req -new -x509 -days 3650 -key ca.key -out ca.crt -subj "/CN=yngwie proxy CA"
	openssl genrsa -out cert.key 2048
	mkdir certs/
	mkdir serial_numbers/

.PHONY: add-trusted-cert
add-trusted-cert: ca.crt
	sudo cp ca.crt /usr/local/share/ca-certificates/
	sudo update-ca-certificates -v

.PHONY: docker-build
docker-build: ./ca.key ./ca.crt ./cert.key ./certs/ ./serial_numbers/
	docker build -t proxy-server .
	docker build -t proxy-api -f src/Dockerfile .

.PHONY: docker-compose-up
docker-compose-up: docker-build
	docker compose up -d

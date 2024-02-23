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

.PHONY: docker-run
docker-run: docker-build
	docker run -d -p 8080:8080 --name my-proxy-server proxy-server

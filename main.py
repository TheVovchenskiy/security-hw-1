from src.proxy import HttpProxyServer


if __name__ == '__main__':
    proxy_server = HttpProxyServer()
    proxy_server.run()

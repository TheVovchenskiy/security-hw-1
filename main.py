from src.proxy import ProxyServer


if __name__ == '__main__':
    try:
        proxy_server = ProxyServer()
        proxy_server.run()
    except Exception as e:
        print(f'Unexpected error: {e}')

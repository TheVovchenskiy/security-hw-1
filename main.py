from src.proxy import HttpProxyServer


if __name__ == '__main__':
    try:
        proxy_server = HttpProxyServer()
        proxy_server.run()
    except Exception as e:
        print(f'Unexpected error: {e}')

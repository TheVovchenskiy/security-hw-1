from http.client import HTTPConnection
from urllib.parse import urlencode


class Scanner:
    @staticmethod
    def scan_sql_injection(parsed_request):
        vulnerable_params = []
        test_payloads = ["'", '"']
        original_path = parsed_request['path']
        for payload in test_payloads:
            for param_type in ['get_params', 'post_params', 'cookies']:
                for param, value in parsed_request[param_type].items():
                    test_params = parsed_request[param_type].copy()
                    test_params[param] = value + payload

                    test_headers = parsed_request['headers']

                    test_path = Scanner._construct_path_with_params(
                        original_path,
                        test_params,
                    ) if param_type == 'get_params' else original_path

                    test_body = urlencode(test_params).encode() \
                        if param_type == 'post_params' else None

                    if param_type == 'cookies':
                        test_headers['Cookie'] = '; '.join([
                            f"{k}={v}" for k, v in test_params.items()
                        ])

                    response = Scanner._send_test_request(
                        parsed_request['method'],
                        test_path,
                        test_body,
                        test_headers,
                    )

                    if Scanner._is_response_different(
                        response,
                        parsed_request['response'],
                    ):
                        vulnerable_params.append((param_type, param))
        return vulnerable_params

    @staticmethod
    def _construct_path_with_params(path, params):
        return path + '?' + urlencode(params)

    @staticmethod
    def _send_test_request(self, method, path, body, headers):
        conn = HTTPConnection(self.headers['Host'])
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        conn.close()
        return response

    @staticmethod
    def _is_response_different(self, test_response, original_response):
        return (test_response.status != original_response['code'] or
                len(test_response.read()) != len(original_response['body']))

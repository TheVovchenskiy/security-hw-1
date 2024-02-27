from http.client import HTTPSConnection

from src.proxy import Response


conn = HTTPSConnection('github.com')

conn.request(
    'GET',
    '/',
    None,
    {"Host": "github.com", "User-Agent": "curl/7.81.0", "Accept": "*/*"}
)

response = Response(conn.getresponse())

print(response.body)

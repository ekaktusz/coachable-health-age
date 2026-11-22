from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
import unittest
from urllib.error import HTTPError

from google_health import HealthMCP, validate_endpoint


class TransportTests(unittest.TestCase):
    def test_plaintext_requires_explicit_loopback(self):
        for endpoint, allowed in [('http://127.0.0.1:3333/mcp', False),
                                  ('http://example.test/mcp', True),
                                  ('https://user:pass@example.test/mcp', False)]:
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                validate_endpoint(endpoint, allowed)
        validate_endpoint('http://127.0.0.1:3333/mcp', True)
        validate_endpoint('https://example.test/mcp', False)

    def test_rpc_rejects_redirects(self):
        hits = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                hits.append('POST')
                self.send_response(302)
                self.send_header('Location', '/redirect-target')
                self.end_headers()

            def do_GET(self):
                hits.append('GET')
                self.send_response(200)
                self.end_headers()

            def log_message(self, *_):
                pass

        with HTTPServer(('127.0.0.1', 0), Handler) as server:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with self.assertRaises(HTTPError) as error:
                    HealthMCP(f'http://127.0.0.1:{server.server_port}/mcp', allow_loopback_http=True)
                self.assertEqual(error.exception.code, 302)
                error.exception.close()
                self.assertEqual(hits, ['POST'])
            finally:
                server.shutdown()
                thread.join()

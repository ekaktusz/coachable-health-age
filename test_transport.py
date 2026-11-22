import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
import unittest
from urllib.error import HTTPError

from google_health import HealthMCP, validate_endpoint


class TransportTests(unittest.TestCase):
    def initialize_with_response(self, content_type, make_body):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if 'id' not in request:
                    self.send_response(202)
                    self.end_headers()
                    return
                body = make_body(request['id'])
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_):
                pass

        with HTTPServer(('127.0.0.1', 0), Handler) as server:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                client = HealthMCP(f'http://127.0.0.1:{server.server_port}/mcp', allow_loopback_http=True)
                return client.headers['MCP-Protocol-Version']
            finally:
                server.shutdown()
                thread.join()

    def test_sse_joins_multiple_data_lines_and_skips_notifications(self):
        def payload(rpc_id):
            return (f': ping\n\ndata: {{"jsonrpc":"2.0","method":"notifications/message"}}\n\n'
                    f'event: message\ndata: {{"jsonrpc":"2.0","id":{rpc_id},\n'
                    f'data: "result":{{"protocolVersion":"2025-06-18"}}}}\n\n').encode()
        self.assertEqual(self.initialize_with_response('text/event-stream', payload), '2025-06-18')

    def test_json_response_must_match_request_id(self):
        def payload(rpc_id):
            return json.dumps({'jsonrpc': '2.0', 'id': rpc_id + 1,
                               'result': {'protocolVersion': '2025-06-18'}}).encode()
        with self.assertRaisesRegex(ValueError, 'matching MCP response'):
            self.initialize_with_response('application/json', payload)

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

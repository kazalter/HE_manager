import http.client
import json
import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from time import monotonic
from unittest.mock import patch

from app.services.external.pawchive import account, client


class FavoritesRetryTests(unittest.TestCase):
    def setUp(self):
        self.responses = []
        self.requests = []
        self.connections = []
        self.received_responses = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                owner.requests.append((self.path, self.client_address[1], self.headers.get('Cookie')))
                status, body = owner.responses.pop(0)
                if status == 'disconnect':
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                if status == 'stall':
                    threading.Event().wait(0.2)
                    self.close_connection = True
                    return
                if str(status).startswith('stall_body'):
                    self.send_response(int(str(status).rsplit('_',1)[-1]) if status != 'stall_body' else 200)
                    self.send_header('Content-Length', '100')
                    self.end_headers()
                    try:
                        self.wfile.write(b'[')
                        self.wfile.flush()
                    except OSError:
                        return
                    threading.Event().wait(0.2)
                    self.close_connection = True
                    return
                if status == 'drip':
                    body = b'[]' + b' ' * 40
                    self.send_response(200)
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    for value in body:
                        try:
                            self.wfile.write(bytes([value]))
                            self.wfile.flush()
                        except OSError:
                            break
                        threading.Event().wait(0.01)
                    return
                if status == 'drip_headers':
                    wire = b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n[]'
                    for value in wire:
                        try:
                            self.connection.sendall(bytes([value]))
                        except OSError:
                            break
                        threading.Event().wait(0.01)
                    self.close_connection = True
                    return
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

        def connection(host, *, timeout=20):
            # Use real HTTP/socket I/O at the transport boundary; keep the public
            # Pawchive endpoint, cookies, account parsing and retry logic real.
            class Connection(http.client.HTTPConnection):
                def getresponse(self):
                    response = super().getresponse()
                    owner.received_responses.append(response)
                    return response
            result = Connection('127.0.0.1', self.server.server_port, timeout=min(timeout, 0.05))
            owner.connections.append(result)
            return result

        self.connection_patch = patch.object(client, '_new_connection', side_effect=connection)
        self.connection_patch.start()
        self.session = account.AccountSession(cookies={'session': 'test-only-cookie'})
        self.favorite = json.dumps([{'service':'fanbox','id':'author-7','name':'Sample author'}]).encode()

    def tearDown(self):
        self.connection_patch.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_temporary_http_failure_recovers_with_a_new_connection(self):
        self.responses = [(503, b'busy'), (200, self.favorite)]
        items = account._fetch_favorites(self.session)
        self.assertEqual([item['creator_name'] for item in items], ['Sample author'])
        self.assertEqual(len(self.requests), 2)
        self.assertTrue(all(request[2] == 'session=test-only-cookie' for request in self.requests))
        self.assertNotEqual(self.requests[0][1], self.requests[1][1])
        self.assertTrue(all(connection.sock is None for connection in self.connections))

    def test_disconnected_connection_is_closed_and_replaced(self):
        self.responses = [('disconnect', b''), (200, self.favorite)]
        self.assertEqual(account._fetch_favorites(self.session)[0]['creator_id'], 'author-7')
        self.assertEqual(len(self.requests), 2)
        self.assertTrue(all(connection.sock is None for connection in self.connections))

    def test_stalled_request_times_out_and_retries(self):
        self.responses = [('stall', b''), (200, self.favorite)]
        self.assertEqual(account._fetch_favorites(self.session)[0]['creator_id'], 'author-7')
        self.assertEqual(len(self.requests), 2)

    def test_timed_out_body_response_is_closed(self):
        self.responses = [('stall_body', b'')]
        with self.assertRaises(client.PawchiveError):
            client.account_request('/api/v1/account/favorites?type=artist', cookies=self.session.cookies)
        self.assertTrue(self.received_responses[0].closed)

    def test_known_auth_access_and_rate_limit_headers_stop_even_if_body_stalls(self):
        for status, code in [(401,'ACCOUNT_AUTH_REQUIRED'),(403,'ACCESS_RESTRICTED'),(429,'RATE_LIMITED')]:
            with self.subTest(status=status):
                before = len(self.requests)
                self.responses = [(f'stall_body_{status}', b''), (200, self.favorite)]
                with self.assertRaises(client.PawchiveError) as raised:
                    account._fetch_favorites(self.session)
                self.assertEqual(raised.exception.code, code)
                self.assertEqual(len(self.requests)-before, 1)

    def test_continuous_slow_body_cannot_hold_the_account_read_forever(self):
        self.responses = [('drip', b'')]
        with patch.object(account, '_FAVORITES_RETRY_WINDOW', 0.06), patch.object(client, '_next_api_request', 0.0):
            with self.assertRaises(client.PawchiveError):
                account._fetch_favorites(self.session)
        self.assertEqual(len(self.requests), 1)
        self.assertTrue(self.received_responses[0].closed)

    def test_throttle_wait_cannot_start_a_request_after_its_time_budget(self):
        self.responses = [(200, self.favorite)]
        with patch.object(account, '_FAVORITES_RETRY_WINDOW', 0.06), patch.object(client, '_next_api_request', monotonic()+1.0):
            with self.assertRaises(client.PawchiveError):
                account._fetch_favorites(self.session)
        self.assertEqual(len(self.requests), 0)

    def test_continuous_slow_headers_are_interrupted_at_the_deadline(self):
        self.responses = [('drip_headers', b'')]
        started = monotonic()
        with patch.object(client, '_next_api_request', 0.0):
            with self.assertRaises(client.PawchiveError):
                client.account_request('/api/v1/account/favorites?type=artist', budget=0.06)
        self.assertLess(monotonic() - started, 0.25)
        self.assertTrue(all(connection.sock is None for connection in self.connections))

    def test_temporary_invalid_response_can_recover(self):
        self.responses = [(200, b'<html>temporarily unavailable</html>'), (200, self.favorite)]
        self.assertEqual(account._fetch_favorites(self.session)[0]['creator_id'], 'author-7')

    def test_persistent_failure_stops_after_initial_request_and_two_retries(self):
        self.responses = [(503, b'busy')] * 4
        with self.assertRaises(client.PawchiveError) as raised:
            account._fetch_favorites(self.session)
        self.assertEqual(raised.exception.code, 'UPSTREAM_UNAVAILABLE')
        self.assertEqual(len(self.requests), 3)
        self.assertTrue(all(connection.sock is None for connection in self.connections))

    def test_auth_access_and_rate_limit_failures_are_not_retried(self):
        for status, code in [(401,'ACCOUNT_AUTH_REQUIRED'),(403,'ACCESS_RESTRICTED'),(429,'RATE_LIMITED')]:
            with self.subTest(status=status):
                before = len(self.requests)
                self.responses = [(status, b'blocked'), (200, self.favorite)]
                with self.assertRaises(client.PawchiveError) as raised:
                    account._fetch_favorites(self.session)
                self.assertEqual(raised.exception.code, code)
                self.assertEqual(len(self.requests)-before, 1)

    def test_retry_window_stops_further_requests_after_slow_failures(self):
        self.responses = [(503, b'busy')] * 4
        ticks = iter([0, 0, 0, 1, 31])
        with patch.object(account, 'monotonic', side_effect=lambda: next(ticks, 31), create=True):
            with self.assertRaises(client.PawchiveError):
                account._fetch_favorites(self.session)
        self.assertEqual(len(self.requests), 2)

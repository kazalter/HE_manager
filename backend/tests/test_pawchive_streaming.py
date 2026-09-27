import unittest
from unittest.mock import patch

from app.auth import query_token_allowed
from app.routers.pawchive import stream_media_response
from app.services.external.pawchive import client, refs

IMAGE = "/ab/cd/" + "a" * 64 + ".jpg"
VIDEO = "/01/23/" + "b" * 64 + ".mp4"


class FakeConnection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeResponse:
    def __init__(self, status, content_type, content_range=None):
        self.status = status
        self.headers = {"Content-Type": content_type, "Content-Length": "16"}
        if content_range:
            self.headers["Content-Range"] = content_range

    def getheader(self, name):
        return self.headers.get(name)

    def read(self, size):
        return b""


class StreamTests(unittest.TestCase):
    def test_range_status_and_headers_follow_upstream(self):
        token = refs.sign_media(VIDEO, "video")
        for status, content_range in ((200, None), (206, "bytes 0-15/100")):
            connection = FakeConnection()
            with patch.object(client, "open_media", return_value=(connection, FakeResponse(status, "video/mp4", content_range))):
                response = stream_media_response(token, "bytes=0-15")
            self.assertEqual(response.status_code, status)
            self.assertEqual(response.headers.get("content-range"), content_range)
            self.assertIsNone(response.headers.get("set-cookie"))
            response.background.func()
            self.assertTrue(connection.closed)

    def test_416_preserves_unsatisfied_range(self):
        connection = FakeConnection()
        with patch.object(client, "open_media", return_value=(connection, FakeResponse(416, "video/mp4", "bytes */100"))):
            response = stream_media_response(refs.sign_media(VIDEO, "video"), "bytes=200-")
        self.assertEqual(response.status_code, 416)
        self.assertEqual(response.headers["content-range"], "bytes */100")
        self.assertTrue(connection.closed)

    def test_invalid_ref_and_html_are_rejected(self):
        with self.assertRaises(client.PawchiveError):
            stream_media_response("arbitrary-url")
        connection = FakeConnection()
        with patch.object(client, "open_media", return_value=(connection, FakeResponse(200, "text/html"))):
            with self.assertRaises(client.PawchiveError):
                stream_media_response(refs.sign_media(IMAGE, "image"))
        self.assertTrue(connection.closed)

    def test_query_token_only_on_binary_route(self):
        self.assertTrue(query_token_allowed("GET", "/external/pawchive/media/signed"))
        self.assertFalse(query_token_allowed("POST", "/external/pawchive/media/signed"))
        self.assertFalse(query_token_allowed("GET", "/external/pawchive/posts"))


if __name__ == "__main__":
    unittest.main()

import argparse
import io
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import speedtest


class DownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Handler(BaseHTTPRequestHandler):
            requests = 0
            active = 0
            max_active = 0
            body = b"x" * (speedtest.CHUNK_SIZE * 2 + 17)

            def do_GET(self):
                type(self).requests += 1
                type(self).active += 1
                type(self).max_active = max(self.active, self.max_active)
                try:
                    if self.path == "/error":
                        self.send_error(503)
                        return
                    self.send_response(200)
                    # No Content-Length: the client must count actual bytes.
                    self.send_header("Content-Type", "application/octet-stream")
                    self.end_headers()
                    self.wfile.write(self.body)
                    self.wfile.flush()
                finally:
                    type(self).active -= 1

            def log_message(self, *_args):
                pass

        cls.handler = Handler
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.handler.requests = self.handler.active = self.handler.max_active = 0

    def test_ten_sequential_downloads_and_actual_byte_count(self):
        output, errors = io.StringIO(), io.StringIO()
        self.assertEqual(speedtest.run(self.url + "/file", 2, output, errors), 0)
        self.assertEqual(self.handler.requests, 10)
        self.assertEqual(self.handler.max_active, 1)
        self.assertIn(f"Downloaded: {10 * len(self.handler.body)} bytes", output.getvalue())
        self.assertIn("Average request time:", output.getvalue())
        self.assertIn("MB/s", output.getvalue())
        self.assertIn("Mbit/s", output.getvalue())
        self.assertEqual(errors.getvalue(), "")

    def test_http_failure_is_not_reported_as_success(self):
        output, errors = io.StringIO(), io.StringIO()
        self.assertEqual(speedtest.run(self.url + "/error", 2, output, errors), 1)
        self.assertEqual(self.handler.requests, 1)
        self.assertIn("503", errors.getvalue())
        self.assertNotIn("Speed:", output.getvalue())


class CalculationTests(unittest.TestCase):
    def test_aggregate_speed_is_total_bytes_over_total_time(self):
        result = speedtest.summarize([
            speedtest.Measurement(1, 2_000_000),
            speedtest.Measurement(3, 2_000_000),
        ])
        self.assertEqual(result.average_seconds, 2)
        self.assertEqual(result.megabytes_per_second, 1)

    def test_reject_invalid_inputs(self):
        for value in ("file:///etc/hosts", "https://", "https://host:abc/a",
                      "http://name:secret@host/a"):
            with self.subTest(url=value), self.assertRaises(argparse.ArgumentTypeError):
                speedtest.http_url(value)
        for value in ("0", "-1", "nan", "inf", "abc"):
            with self.subTest(timeout=value), self.assertRaises(argparse.ArgumentTypeError):
                speedtest.positive_timeout(value)


if __name__ == "__main__":
    unittest.main()

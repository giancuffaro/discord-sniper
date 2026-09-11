import os
import tempfile
import unittest

import health


class WebullStreamHealthTests(unittest.TestCase):
    def _read(self, text):
        fd, path = tempfile.mkstemp(suffix=".log")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
            return health.webull_stream_from_log(path)
        finally:
            os.unlink(path)

    def test_retry_storm_after_latest_start_is_unhealthy(self):
        state = self._read(
            "[stream] connected (old)\n"
            "STREAM on - stock prices pushed over MQTT\n"
            "webull.data ERROR Peer sent no certificates to verify\n"
            "webull.data INFO next retry will be started in 10000 ms\n")
        self.assertFalse(state["healthy"])
        self.assertEqual(state["tls_errors"], 1)
        self.assertEqual(state["retries"], 1)

    def test_recovery_after_errors_is_healthy(self):
        state = self._read(
            "STREAM on - stock prices pushed over MQTT\n"
            "webull.data ERROR Peer sent no certificates to verify\n"
            "[stream] connected (new) - 12 symbols wanted\n")
        self.assertTrue(state["healthy"])
        self.assertEqual(state["last"], "connected")


if __name__ == "__main__":
    unittest.main()

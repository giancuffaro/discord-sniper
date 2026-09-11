import ssl
import unittest

import stream_bus


class StreamTlsTests(unittest.TestCase):
    def test_paho_context_keeps_verification_and_supports_deferred_handshake(self):
        context = stream_bus.paho_compatible_tls_context()
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertEqual(type(context).__module__, "ssl")


if __name__ == "__main__":
    unittest.main()

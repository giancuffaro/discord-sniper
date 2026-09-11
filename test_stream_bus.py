import ssl
import unittest

import paho.mqtt.client as mqtt

import stream_bus


class StreamTlsTests(unittest.TestCase):
    def test_paho_context_keeps_verification_and_supports_deferred_handshake(self):
        context = stream_bus.paho_compatible_tls_context()
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertEqual(type(context).__module__, "ssl")

        client = mqtt.Client(client_id="context-replacement-test")
        client.tls_set()
        client._ssl_context = context
        self.assertIs(client._ssl_context, context)


if __name__ == "__main__":
    unittest.main()

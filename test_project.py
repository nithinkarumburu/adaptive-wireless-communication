import unittest
from src.coding import adaptive_encode, decode
from src.ldpc import encode_block, syndrome, simulate_ldpc
import numpy as np

class ProjectTests(unittest.TestCase):
    def test_ldpc_codeword_satisfies_checks(self):
        rng = np.random.default_rng(5)
        for _ in range(5):
            word = encode_block(rng.integers(0, 2, size=64, dtype=np.uint8))
            self.assertEqual(int(np.sum(syndrome(word))), 0)

    def test_adaptive_codec_roundtrip(self):
        payload = (b"wireless communication and LDPC lab " * 30)
        codec, encoded, _ = adaptive_encode(payload)
        self.assertEqual(decode(codec, encoded), payload)

    def test_channel_simulation_returns_metrics(self):
        result = simulate_ldpc(b"hello", snr_db=18.0, seed=9)
        self.assertIn("raw_ber", result)
        self.assertIn("post_ldpc_ber", result)
        self.assertEqual(len(result["recovered_bytes"]), 5)

if __name__ == "__main__":
    unittest.main()

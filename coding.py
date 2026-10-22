"""Adaptive source coding using a small ANN trained on synthetic payloads."""
from __future__ import annotations
import bz2, json, lzma, zlib
from functools import lru_cache
from typing import Callable
import numpy as np
from sklearn.neural_network import MLPClassifier

CODEC_NAMES = ["zlib", "bz2", "lzma", "raw"]

def encode(codec: str, data: bytes) -> bytes:
    if codec == "zlib": return zlib.compress(data, level=6)
    if codec == "bz2": return bz2.compress(data, compresslevel=5)
    if codec == "lzma": return lzma.compress(data, preset=3)
    if codec == "raw": return data
    raise ValueError(f"Unknown codec: {codec}")

def decode(codec: str, data: bytes) -> bytes:
    if codec == "zlib": return zlib.decompress(data)
    if codec == "bz2": return bz2.decompress(data)
    if codec == "lzma": return lzma.decompress(data)
    if codec == "raw": return data
    raise ValueError(f"Unknown codec: {codec}")

def features(data: bytes) -> np.ndarray:
    if not data: data = b"\x00"
    a = np.frombuffer(data, dtype=np.uint8)
    counts = np.bincount(a, minlength=256).astype(float)
    p = counts[counts > 0] / len(a)
    entropy = float(-(p * np.log2(p)).sum()) / 8.0
    adjacent_repeat = float(np.mean(a[1:] == a[:-1])) if len(a) > 1 else 0.0
    printable = float(np.mean((a >= 32) & (a <= 126)))
    return np.array([
        entropy,
        float(np.var(a) / (255.0**2)),
        float(np.mean(a == 0)),
        adjacent_repeat,
        float(len(np.unique(a)) / 256.0),
        printable,
        min(len(a), 65536) / 65536.0,
        float(counts.max() / len(a)),
    ], dtype=np.float32)

def _synthetic_payloads(seed: int = 123, n: int = 320):
    rng = np.random.default_rng(seed)
    samples: list[bytes] = []
    for i in range(n):
        size = int(rng.integers(48, 1200))
        kind = i % 6
        if kind == 0:
            base = bytes(rng.choice(np.array(list(b"abcdef0123456789 ")), size=size).tolist())
        elif kind == 1:
            token = rng.choice([b"sensor=", b"temp=", b"status=", b"value="])
            rows = [token + str(float(rng.normal(20, 4))).encode() + b";" for _ in range(max(1, size // 18))]
            base = b"".join(rows)[:size]
        elif kind == 2:
            obj = {f"field_{j}": [int(x) for x in rng.integers(0, 10, size=8)] for j in range(max(1, size // 80))}
            base = json.dumps(obj, separators=(",", ":")).encode()[:size]
        elif kind == 3:
            pattern = rng.choice([b"ABAB0011", b"HELLO_WORLD_", b"00000000", b"<packet><data>"])
            base = (pattern * (size // len(pattern) + 1))[:size]
        elif kind == 4:
            base = rng.integers(0, 8, size=size, dtype=np.uint8).tobytes()
        else:
            base = rng.integers(0, 256, size=size, dtype=np.uint8).tobytes()
        samples.append(base)
    return samples

@lru_cache(maxsize=1)
def get_ann_model() -> MLPClassifier:
    """Train a compact codec selector. Label is the shortest encoded candidate."""
    xs, ys = [], []
    for payload in _synthetic_payloads():
        lens = [len(encode(c, payload)) for c in CODEC_NAMES]
        xs.append(features(payload))
        ys.append(int(np.argmin(lens)))
    model = MLPClassifier(hidden_layer_sizes=(32, 16), activation="relu", solver="adam",
                          max_iter=350, random_state=42, early_stopping=True,
                          validation_fraction=0.15, n_iter_no_change=18)
    model.fit(np.vstack(xs), np.asarray(ys))
    return model

def adaptive_encode(data: bytes) -> tuple[str, bytes, dict]:
    model = get_ann_model()
    probs = model.predict_proba(features(data).reshape(1, -1))[0]
    codec_idx = int(np.argmax(probs))
    codec = CODEC_NAMES[codec_idx]
    encoded = encode(codec, data)
    all_lengths = {name: len(encode(name, data)) for name in CODEC_NAMES}
    # Keep raw pass-through if compressed output is larger.
    if all_lengths[codec] >= len(data):
        codec, encoded = "raw", data
    return codec, encoded, {"ann_confidence": float(np.max(probs)), "candidate_bytes": all_lengths}

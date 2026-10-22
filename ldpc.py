"""Educational systematic (128,64) sparse parity-check code and min-sum decoder.

This is a reproducible lab implementation, not a standards-compliant Wi-Fi LDPC code.
"""
from __future__ import annotations
import numpy as np

N, K = 128, 64

def parity_matrix(seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    p = np.zeros((K, K), dtype=np.uint8)
    for col in range(K):
        rows = rng.choice(K, size=3, replace=False)
        p[rows, col] = 1
    return p

_P = parity_matrix()
_H = np.concatenate([_P.T, np.eye(K, dtype=np.uint8)], axis=1)


def encode_block(info_bits: np.ndarray) -> np.ndarray:
    u = np.asarray(info_bits, dtype=np.uint8).reshape(-1)
    if len(u) != K: raise ValueError("LDPC information block must contain 64 bits")
    parity = (u @ _P) % 2
    return np.concatenate([u, parity.astype(np.uint8)])

def syndrome(bits: np.ndarray) -> np.ndarray:
    return (_H @ np.asarray(bits, dtype=np.uint8).reshape(-1)) % 2

def decode_block(llr: np.ndarray, max_iter: int = 25, alpha: float = 0.8) -> tuple[np.ndarray, int, bool]:
    """Normalized min-sum decoding; positive LLR favors bit 0."""
    llr = np.asarray(llr, dtype=float).reshape(N)
    check_edges = [np.flatnonzero(_H[r]) for r in range(K)]
    var_edges = [np.flatnonzero(_H[:, c]) for c in range(N)]
    # Messages indexed by (check, variable), represented as dense K x N arrays.
    q = np.zeros((K, N), dtype=float)
    rmsg = np.zeros((K, N), dtype=float)
    for c in range(K):
        q[c, check_edges[c]] = llr[check_edges[c]]
    posterior = llr.copy()
    for it in range(1, max_iter + 1):
        for c, vars_ in enumerate(check_edges):
            vals = q[c, vars_]
            signs = np.sign(vals); signs[signs == 0] = 1.0
            absvals = np.abs(vals)
            if len(absvals) == 0: continue
            min_idx = int(np.argmin(absvals))
            min1 = absvals[min_idx]
            min2 = float(np.min(np.delete(absvals, min_idx))) if len(absvals) > 1 else min1
            total_sign = float(np.prod(signs))
            for j, v in enumerate(vars_):
                magnitude = min2 if j == min_idx else min1
                rmsg[c, v] = alpha * total_sign * signs[j] * magnitude
        posterior = llr.copy()
        for v in range(N):
            cs = var_edges[v]
            if len(cs): posterior[v] += rmsg[cs, v].sum()
        hard = (posterior < 0).astype(np.uint8)
        if not np.any(syndrome(hard)):
            return hard, it, True
        for c, vars_ in enumerate(check_edges):
            for v in vars_:
                q[c, v] = posterior[v] - rmsg[c, v]
    return (posterior < 0).astype(np.uint8), max_iter, False

def bytes_to_bits(data: bytes) -> np.ndarray:
    return np.unpackbits(np.frombuffer(data, dtype=np.uint8))

def bits_to_bytes(bits: np.ndarray) -> bytes:
    bits = np.asarray(bits, dtype=np.uint8).reshape(-1)
    if len(bits) % 8: bits = np.pad(bits, (0, 8 - len(bits) % 8))
    return np.packbits(bits).tobytes()

def simulate_ldpc(data: bytes, snr_db: float = 8.0, seed: int = 42) -> dict:
    """Transmit compressed bytes over simulated BPSK + Rayleigh + AWGN, then decode."""
    rng = np.random.default_rng(seed)
    source_bits = bytes_to_bits(data)
    pad = (-len(source_bits)) % K
    info = np.pad(source_bits, (0, pad))
    info_blocks = info.reshape(-1, K) if len(info) else np.zeros((1, K), dtype=np.uint8)
    tx_blocks = np.vstack([encode_block(b) for b in info_blocks])
    tx = tx_blocks.reshape(-1)
    snr = 10.0 ** (snr_db / 10.0)
    noise_sigma = np.sqrt(1.0 / (2.0 * snr))
    # Unit-average-power Rayleigh amplitude and perfect receiver channel knowledge.
    h = np.sqrt(rng.exponential(scale=1.0, size=len(tx)))
    symbols = 1.0 - 2.0 * tx.astype(float)
    y = h * symbols + rng.normal(0.0, noise_sigma, size=len(tx))
    llr = 2.0 * h * y / (noise_sigma ** 2)
    raw_hat = (llr < 0).astype(np.uint8)
    decoded, iterations, syndrome_ok = [], [], []
    for i in range(len(tx_blocks)):
        dec, n_iter, ok = decode_block(llr[i*N:(i+1)*N])
        decoded.append(dec[:K]); iterations.append(n_iter); syndrome_ok.append(ok)
    decoded_bits = np.concatenate(decoded)[:len(source_bits)]
    recovered = bits_to_bytes(decoded_bits)[:len(data)]
    raw_ber = float(np.mean(raw_hat != tx)) if len(tx) else 0.0
    post_ber = float(np.mean(decoded_bits != source_bits)) if len(source_bits) else 0.0
    return {
        "snr_db": float(snr_db), "raw_ber": raw_ber, "post_ldpc_ber": post_ber,
        "syndrome_success_rate": float(np.mean(syndrome_ok)),
        "avg_iterations": float(np.mean(iterations)), "coded_bits": int(len(tx)),
        "information_bits": int(len(source_bits)), "recovered_bytes": recovered,
        "simulation_exact_match": bool(recovered == data),
    }

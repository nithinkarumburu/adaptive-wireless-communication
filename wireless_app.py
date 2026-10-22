"""Wireless Communication & Information Theory Lab: real LAN messaging + simulated PHY metrics."""
from __future__ import annotations
import base64, json, socket, struct, threading, time
from datetime import datetime
from pathlib import Path
import streamlit as st
st.set_page_config(page_title="Wireless Communication & Information Theory Lab", page_icon="📡", layout="wide")
from src.coding import adaptive_encode, decode
from src.ldpc import simulate_ldpc

APP_TITLE = "Wireless Communication & Information Theory Lab"
DEFAULT_PORT = 5000
MAX_PACKET_BYTES = 4 * 1024 * 1024
@st.cache_resource
def get_runtime() -> dict:
    # Persist listener/thread state across Streamlit script reruns.
    return {
        "received": [],
        "lock": threading.Lock(),
        "server_thread": None,
        "stop_event": threading.Event(),
        "server_status": {"running": False, "error": "", "host": "0.0.0.0", "port": DEFAULT_PORT},
    }

_RUNTIME = get_runtime()


def local_ipv4() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _recv_exact(conn: socket.socket, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        part = conn.recv(size - len(chunks))
        if not part:
            raise ConnectionError("Sender disconnected before full packet arrived")
        chunks.extend(part)
    return bytes(chunks)


def _receiver_loop(host: str, port: int) -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind((host, port))
        server.listen(8)
        server.settimeout(0.5)
        _RUNTIME["server_status"].update(running=True, error="", host=host, port=port)
        while not _RUNTIME["stop_event"].is_set():
            try:
                conn, addr = server.accept()
            except socket.timeout:
                continue
            except OSError:
                if _RUNTIME["stop_event"].is_set(): break
                raise
            with conn:
                conn.settimeout(10)
                try:
                    header = _recv_exact(conn, 4)
                    size = struct.unpack("!I", header)[0]
                    if size <= 0 or size > MAX_PACKET_BYTES:
                        raise ValueError(f"Invalid packet size: {size}")
                    packet = json.loads(_recv_exact(conn, size).decode("utf-8"))
                    packet["_peer_ip"] = addr[0]
                    packet["_received_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
                    with _RUNTIME["lock"]:
                        _RUNTIME["received"].insert(0, packet)
                        del _RUNTIME["received"][100:]
                    conn.sendall(b"OK")
                except Exception as exc:
                    try: conn.sendall(("ERROR: " + str(exc)).encode("utf-8")[:500])
                    except OSError: pass
    except Exception as exc:
        _RUNTIME["server_status"]["error"] = str(exc)
    finally:
        _RUNTIME["server_status"]["running"] = False
        try: server.close()
        except OSError: pass


def start_receiver(host: str = "0.0.0.0", port: int = DEFAULT_PORT) -> None:
    thread = _RUNTIME["server_thread"]
    if thread and thread.is_alive():
        return
    _RUNTIME["stop_event"].clear()
    thread = threading.Thread(target=_receiver_loop, args=(host, port), daemon=True)
    _RUNTIME["server_thread"] = thread
    thread.start()
    time.sleep(0.15)


def stop_receiver() -> None:
    _RUNTIME["stop_event"].set()
    # Wake accept() promptly so the thread can exit.
    try:
        with socket.create_connection(("127.0.0.1", DEFAULT_PORT), timeout=0.15):
            pass
    except OSError:
        pass


def send_packet(host: str, port: int, packet: dict) -> tuple[bool, str]:
    raw = json.dumps(packet, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_PACKET_BYTES:
        return False, "Message is too large for this demo (maximum packet size is 4 MiB)."
    try:
        with socket.create_connection((host, port), timeout=5) as conn:
            conn.settimeout(10)
            conn.sendall(struct.pack("!I", len(raw)) + raw)
            response = conn.recv(512).decode("utf-8", errors="replace")
        if response == "OK":
            return True, "Receiver acknowledged the packet."
        return False, response or "Receiver closed without an acknowledgement."
    except OSError as exc:
        return False, f"Could not connect to {host}:{port}. Check both laptops are on the same Wi-Fi and allow TCP port {port} through the receiver firewall. Details: {exc}"


def build_packet(message: str, snr_db: float, seed: int) -> tuple[dict, dict]:
    original = message.encode("utf-8")
    codec, compressed, ann_info = adaptive_encode(original)
    sim = simulate_ldpc(compressed, snr_db=snr_db, seed=seed)
    # Decompression is only attempted when the simulated coded payload recovered exactly.
    simulated_message_ok = False
    if sim["simulation_exact_match"]:
        try: simulated_message_ok = decode(codec, sim["recovered_bytes"]) == original
        except Exception: simulated_message_ok = False
    metrics = {
        "codec": codec,
        "ann_confidence": round(ann_info["ann_confidence"], 4),
        "original_bytes": len(original),
        "compressed_bytes": len(compressed),
        "compression_ratio": round(len(original) / max(1, len(compressed)), 4),
        "bit_saving_pct": round((1 - len(compressed) / max(1, len(original))) * 100, 2),
        "snr_db": sim["snr_db"],
        "raw_ber": sim["raw_ber"],
        "post_ldpc_ber": sim["post_ldpc_ber"],
        "syndrome_success_rate": sim["syndrome_success_rate"],
        "avg_iterations": sim["avg_iterations"],
        "coded_bits": sim["coded_bits"],
        "simulated_payload_exact_match": sim["simulation_exact_match"],
        "simulated_message_integrity": simulated_message_ok,
        "metric_note": "BER and LDPC results are from the simulated Rayleigh + AWGN path, not measured Wi-Fi radio BER.",
    }
    packet = {
        "protocol": "wireless-itc-lab-v1",
        "message_id": f"{int(time.time() * 1000)}-{seed}",
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "message": message,
        "payload_base64": base64.b64encode(original).decode("ascii"),
        "metrics": metrics,
    }
    return packet, metrics


@st.fragment(run_every="1s")
def render_receiver_status_and_history() -> None:
    if _RUNTIME["server_status"]["running"]:
        st.success(f"Receiver listening on 0.0.0.0:{DEFAULT_PORT}. Keep this page open while receiving.")
    elif _RUNTIME["server_status"]["error"]:
        st.error(f"Receiver could not start: {_RUNTIME['server_status']['error']}")
    else:
        st.warning("Receiver is stopped. Click Start receiver before sending from the other laptop.")
    st.caption(f"Share this receiver laptop's IPv4 address with the sender: `{local_ipv4()}`")
    st.divider()
    st.subheader("Message history (auto-refreshes every second)")
    with _RUNTIME["lock"]:
        received = list(_RUNTIME["received"])
    if not received:
        st.caption("No messages received yet.")
    for item in received:
        with st.container(border=True):
            st.markdown(f"**Message:** {item.get('message', '[missing message]')}")
            st.caption(f"Received {item.get('_received_at', 'time unknown')} · Sender IP {item.get('_peer_ip', 'unknown')} · ID {item.get('message_id', 'n/a')}")
            m = item.get("metrics", {})
            cols = st.columns(4)
            cols[0].metric("Codec", m.get("codec", "n/a"))
            cols[1].metric("Compression", f"{m.get('compression_ratio', 0):.2f}×")
            cols[2].metric("Raw BER", f"{m.get('raw_ber', 0):.2e}")
            cols[3].metric("Post-LDPC BER", f"{m.get('post_ldpc_ber', 0):.2e}")
            st.write("Simulated channel integrity:", "✅ Exact" if m.get("simulated_message_integrity") else "⚠️ Not exact / not available")


st.title("📡 Wireless Communication & Information Theory Lab")
st.caption("ANN adaptive source coding · Systematic (128,64) LDPC · Rayleigh fading + AWGN simulation · Real Wi-Fi/LAN messaging")
st.info("Two separate paths are shown: the original message travels reliably over TCP/Wi-Fi; BER and LDPC results are computed on a simulated wireless channel for research metrics.")

send_tab, receiver_tab, about_tab = st.tabs(["📤 Send + Wireless Metrics", "📥 Live Receiver", "ℹ️ How it works"])

with send_tab:
    left, right = st.columns([1.25, 1])
    with left:
        st.subheader("Compose a message")
        with st.form("send_form"):
            target_ip = st.text_input("Receiver laptop IPv4 address", placeholder="e.g. 192.168.1.12")
            port = st.number_input("Receiver port", min_value=1024, max_value=65535, value=DEFAULT_PORT, step=1)
            message = st.text_area("Message to transmit", value="Hello from the wireless communication lab!", height=130)
            snr_db = st.slider("Simulated wireless SNR (dB)", min_value=0.0, max_value=20.0, value=8.0, step=0.5)
            seed = st.number_input("Simulation seed", min_value=0, max_value=2_000_000_000, value=42, step=1)
            submitted = st.form_submit_button("🚀 Transmit message", type="primary", use_container_width=True)
        if submitted:
            if not target_ip.strip():
                st.error("Enter the receiver laptop's IPv4 address.")
            elif not message:
                st.error("Enter a message first.")
            else:
                with st.spinner("Training/loading ANN, simulating LDPC transmission, and sending over Wi-Fi..."):
                    try:
                        packet, metrics = build_packet(message, float(snr_db), int(seed))
                        ok, detail = send_packet(target_ip.strip(), int(port), packet)
                        st.session_state["last_metrics"] = metrics
                        st.session_state["last_send_ok"] = ok
                        st.session_state["last_send_detail"] = detail
                    except Exception as exc:
                        st.session_state["last_send_ok"] = False
                        st.session_state["last_send_detail"] = f"Processing error: {exc}"
        if "last_send_ok" in st.session_state:
            if st.session_state["last_send_ok"]:
                st.success("Message delivered over Wi-Fi. " + st.session_state["last_send_detail"])
            else:
                st.error(st.session_state["last_send_detail"])
    with right:
        st.subheader("Latest transmission metrics")
        metrics = st.session_state.get("last_metrics")
        if metrics:
            a, b = st.columns(2)
            a.metric("Selected codec", metrics["codec"])
            b.metric("Compression ratio", f'{metrics["compression_ratio"]:.2f}×')
            a.metric("Raw channel BER", f'{metrics["raw_ber"]:.3e}')
            b.metric("Post-LDPC BER", f'{metrics["post_ldpc_ber"]:.3e}')
            a.metric("Syndrome success", f'{metrics["syndrome_success_rate"] * 100:.1f}%')
            b.metric("Mean BP iterations", f'{metrics["avg_iterations"]:.1f}')
            st.write("Simulated message integrity:", "✅ Exact" if metrics["simulated_message_integrity"] else "⚠️ Not exact at this SNR")
            st.caption(metrics["metric_note"])
        else:
            st.caption("Send a message to calculate compression and wireless-channel metrics.")
        st.markdown(f"**This laptop's detected LAN IPv4:** `{local_ipv4()}`")
        st.caption("Enter this address on the other laptop when this laptop is running the receiver.")

with receiver_tab:
    st.subheader("Receive and decode messages")
    c1, c2 = st.columns([1, 1])
    with c1:
        st.write(f"Listen address: `0.0.0.0` · Port: `{DEFAULT_PORT}`")
        if st.button("▶ Start receiver", type="primary", use_container_width=True):
            start_receiver()
            time.sleep(0.1)
            st.rerun()
    with c2:
        if st.button("■ Stop receiver", use_container_width=True):
            stop_receiver()
            st.rerun()
    render_receiver_status_and_history()

with about_tab:
    st.subheader("System architecture")
    st.code("""MESSAGE (UTF-8)
   ├── Real network path: TCP/IP over Wi-Fi ───────────────> Receiver displays original message
   └── Research simulation:
       Feature extraction -> ANN codec selection -> zlib/bz2/lzma/raw
       -> systematic (128,64) LDPC -> BPSK
       -> Rayleigh fading + AWGN -> soft min-sum LDPC decoding
       -> decompression/integrity check -> BER and compression metrics""", language="text")
    st.markdown("""
**Important research notes**
- The real message uses TCP, which provides reliable delivery on the network. The receiver's displayed message is not corrupted by the simulated channel.
- The Rayleigh fading + AWGN link is a software simulation. Its BER is not a measurement of the Wi-Fi adapter's physical-layer BER.
- The ANN selector is trained on a small synthetic payload set at first use. For a formal study, train/evaluate it on a documented held-out dataset and save the model.
- The included sparse (128,64) LDPC implementation is educational and is not an IEEE 802.11 Wi-Fi LDPC standard implementation.
- This project is a lab demonstration, not a security protocol. Use it only on a trusted private network; do not expose the receiver port to the public internet.
""")

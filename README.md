# Wireless Communication & Information Theory Lab

A from-scratch Python project with a Streamlit UI, TCP message transfer over a local Wi-Fi/LAN, ANN-selected source compression, an educational systematic (128,64) LDPC code, and a separately simulated BPSK Rayleigh-fading + AWGN channel.

## Requirements
- Python 3.10 or newer (Python 3.12 recommended)
- VS Code
- Both laptops connected to the same trusted Wi-Fi/LAN for a two-laptop demonstration

## Windows setup
Open this folder in VS Code. In Terminal → New Terminal, run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, use Command Prompt terminal and run:

```bat
.venv\Scripts\activate.bat
```

Then start the application:

```powershell
python -m streamlit run wireless_app.py --server.address 0.0.0.0 --server.port 8501
```

Open `http://localhost:8501` in the browser.

## Two-laptop demo
1. On Laptop A, start the app and open **Live Receiver**.
2. Click **Start receiver**. Keep the app running.
3. On Laptop A, note the detected LAN IPv4 address shown on screen.
4. If Windows Firewall prompts, allow Python on **Private networks only**. If it does not prompt, add/allow inbound TCP port `5000` for the Private profile.
5. On Laptop B, install the project and start the app using the same Streamlit command.
6. Open **Send + Wireless Metrics** on Laptop B. Enter Laptop A's IPv4 address, type a message, select SNR and click **Transmit message**.
7. Laptop A should show the received message and the metrics carried with it. Press **Refresh inbox** if the page has not rerun.

Both laptops need to be on the same network. Do not use `127.0.0.1` as the target address on Laptop B; that refers to Laptop B itself. Some campus/guest Wi-Fi networks isolate devices, in which case use a private hotspot or another trusted LAN.

## Run a local smoke test
```powershell
python -m unittest discover -s tests -v
```

## Research interpretation
- TCP/IP over Wi-Fi transfers the original message in the live demonstration.
- BER, syndrome success, and min-sum iteration metrics are computed by a separate software simulation of BPSK over a Rayleigh fading channel with AWGN and perfect channel-state information.
- This educational (128,64) code is not a standards-compliant 802.11 LDPC code. The results should be described as simulated, not measured Wi-Fi physical-layer performance.
- The ANN selector is trained on a reproducible synthetic payload set at first use. For a research submission, document the dataset, train/test split, random seeds, and multiple-run confidence intervals.

## Troubleshooting
- **Address already in use:** close another app using port 5000 or stop the previous receiver process.
- **Connection refused / timeout:** start receiver first, confirm the receiver IP, same Wi-Fi, and firewall rule for TCP 5000.
- **No network connection between laptops:** guest/campus Wi-Fi may enable client isolation; test with a private hotspot.
- **PowerShell activation blocked:** use the Command Prompt activation command above, or run `.venv\\Scripts\\python.exe -m pip install -r requirements.txt` and `.venv\\Scripts\\python.exe -m streamlit run ...` without activating.

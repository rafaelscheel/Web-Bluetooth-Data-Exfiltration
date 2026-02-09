# Web-Bluetooth-Data-Exfiltration

A tool to exfiltrate data from a device over Web Bluetooth for Red-Team exercises.

## Overview

This project provides a BLE GATT server (Linux/BlueZ) and a Web Bluetooth client (HTML/JS) for transferring files over Bluetooth Low Energy.

- **Server** (`server/gatt_server.py`): Python script using BlueZ D-Bus API to advertise a custom GATT service and receive chunked file uploads.
- **Client** (`client/index.html`): Single-page HTML/JS application that uses the Web Bluetooth API to connect to the server and upload files.

## Requirements

### Server (Linux)
- Linux with BlueZ 5.x
- `bluetoothd` running with `--experimental` flag (required for GATT server support)
- Python 3.6+
- `python3-dbus` (dbus-python)
- `python3-gi` (PyGObject / GLib)
- A Bluetooth adapter that supports BLE (Bluetooth 4.0+)

### Client (Browser)
- Chrome, Edge, or Opera (Web Bluetooth is not supported in Firefox or Safari)
- Must be served over HTTPS or `localhost`

## Setup

### 1. Install server dependencies (Debian/Ubuntu)

```bash
sudo apt install bluez python3-dbus python3-gi
```

### 2. Enable BlueZ experimental mode

Edit the BlueZ systemd unit:

```bash
sudo nano /lib/systemd/system/bluetooth.service
```

Change the `ExecStart` line to:

```
ExecStart=/usr/libexec/bluetooth/bluetoothd --experimental
```

Then reload and restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart bluetooth
```

### 3. Run the server

```bash
sudo python3 server/gatt_server.py
```

The server will check for all dependencies and print recommendations for anything missing. Use `--help` for options:

```
usage: gatt_server.py [-h] [--adapter ADAPTER] [--upload-dir UPLOAD_DIR] [--skip-checks]
```

### 4. Serve the client

The client HTML file must be served over HTTPS or from `localhost`. For local testing:

```bash
cd client
python3 -m http.server 8080
```

Then open `http://localhost:8080` in Chrome/Edge.

## Protocol

The file transfer uses two GATT characteristics under a custom service:

| Component | UUID |
|---|---|
| Service | `12345678-1234-5678-1234-56789abcdef0` |
| Control Characteristic | `12345678-1234-5678-1234-56789abcdef1` |
| Data Characteristic | `12345678-1234-5678-1234-56789abcdef2` |

### Transfer sequence

1. Client writes to **Control**: `0x01` + UTF-8 filename bytes (BEGIN)
2. Client writes file content in chunks to **Data**
3. Client writes to **Control**: `0x02` (END — server saves file)

Abort at any time by writing `0x03` to the Control characteristic.

### Chunk size

The default BLE ATT MTU is 23 bytes (20 bytes usable payload). The client defaults to 20-byte chunks. If your BLE stack negotiates a larger MTU, you can increase the chunk size in the client UI (up to 512 bytes).

## Uploaded files

Files are saved to `server/uploads/` by default (configurable with `--upload-dir`). Duplicate filenames are automatically resolved with a numeric suffix.

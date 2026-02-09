# Web-Bluetooth-Data-Exfiltration
A tool to exfiltrate data from a device over web Bluetooth for Red-Team exercises.

## 🚀 Latest: GATT Web Bluetooth File Upload System

This repository now includes a complete implementation of a GATT Web Bluetooth Server for Linux that receives files from web clients.

### Quick Start

**Server (Linux):**
```bash
sudo python3 bluetooth_server.py
```

**Client (Browser):**
1. Open `client.html` in Chrome/Edge (via HTTPS or localhost)
2. Click "Connect to Server"
3. Select a file and upload

### Documentation

See **[USAGE.md](USAGE.md)** for complete documentation including:
- Installation instructions
- System requirements
- Architecture details
- Troubleshooting guide
- Security considerations

### Features

✅ Python GATT server with BlueZ and D-Bus  
✅ Dependency checking and recommendations  
✅ Automatic service advertisement  
✅ File transfer with chunking (512-byte chunks)  
✅ Modern web interface with progress tracking  
✅ Activity logging and error handling  
✅ Directory traversal protection  

### Files

- `bluetooth_server.py` - Python GATT server
- `client.html` - Web interface
- `client.js` - Client-side JavaScript
- `USAGE.md` - Complete documentation 

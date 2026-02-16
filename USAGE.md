# Web Bluetooth GATT Server - File Upload System

A complete implementation of a GATT Web Bluetooth Server for Linux using Python, BlueZ, and D-Bus that allows file uploads from web clients.

## Features

✅ **Python GATT Server**
- Dependency checking (BlueZ, D-Bus, adapters)
- Automatic service advertisement
- File reception with chunking support
- Secure file storage with directory traversal protection

✅ **Web Client**
- Modern, responsive HTML/CSS interface
- File selection and upload
- Progress tracking
- Activity logging
- Chunked file transfer (512-byte chunks)

## Architecture

### GATT Service Structure

**Service UUID:** `12345678-1234-5678-1234-56789abcdef0`

**Characteristics:**
1. **File Name Characteristic** (`12345678-1234-5678-1234-56789abcdef2`)
   - Properties: Read, Write
   - Purpose: Set the name of the file to be uploaded

2. **File Data Characteristic** (`12345678-1234-5678-1234-56789abcdef1`)
   - Properties: Write, Write Without Response
   - Purpose: Transfer file data in chunks (512 bytes max per chunk)

3. **File Control Characteristic** (`12345678-1234-5678-1234-56789abcdef3`)
   - Properties: Read, Write
   - Purpose: Control file transfer flow
   - Commands:
     - `START` - Begin file transfer (clears buffer)
     - `END` - Complete transfer and save file
     - `CANCEL` - Cancel transfer and clear buffer

### File Transfer Protocol

1. Client writes file name to File Name Characteristic
2. Client writes `START` to File Control Characteristic
3. Client writes file data in chunks to File Data Characteristic
4. Client writes `END` to File Control Characteristic
5. Server saves file and responds with status
6. Client reads File Control Characteristic to verify completion

## Requirements

### Server Requirements

- **Operating System:** Linux (tested on Ubuntu/Debian)
- **Python:** 3.6 or higher
- **Dependencies:**
  - BlueZ 5.48 or higher
  - Python packages:
    - `dbus-python`
    - `PyGObject`
  - D-Bus system bus access
  - Bluetooth adapter

### Client Requirements

- **Browser:** Chrome 56+, Edge 79+, or Opera 43+
- **Connection:** HTTPS or localhost
- **Bluetooth:** Enabled on device

## Installation

### 1. Install System Dependencies

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y bluez python3-dbus python3-gi

# Ensure bluetooth service is running
sudo systemctl start bluetooth
sudo systemctl enable bluetooth

# Add your user to the bluetooth group
sudo usermod -a -G bluetooth $USER

# Log out and back in for group changes to take effect
```

### 2. Verify Bluetooth Adapter

```bash
# Check if bluetooth adapter is available
bluetoothctl show

# If powered off, turn it on
bluetoothctl power on
```

### 3. Clone Repository

```bash
git clone https://github.com/rafaelscheel/Web-Bluetooth-Data-Exfiltration.git
cd Web-Bluetooth-Data-Exfiltration
```

## Usage

### Starting the Server

1. Make the server script executable:
```bash
chmod +x bluetooth_server.py
```

2. Run the server (requires root or bluetooth group membership):
```bash
sudo python3 bluetooth_server.py
```

Or if your user is in the bluetooth group:
```bash
python3 bluetooth_server.py
```

3. The server will:
   - Check dependencies
   - Register GATT services
   - Start advertising as "FileTransfer"
   - Create an `uploads/` directory for received files

Expected output:
```
============================================================
GATT Web Bluetooth Server - File Upload Service
============================================================
Checking dependencies...
✓ BlueZ installed: 5.xx
✓ Bluetooth service is active
✓ D-Bus system bus is available
✓ Found 1 Bluetooth adapter(s):
  - /org/bluez/hci0

✓ All dependencies satisfied!

Starting GATT server...
Using adapter: /org/bluez/hci0
Registering GATT application...
GATT application registered
Registering advertisement...
Advertisement registered

============================================================
✓ Server is running!
✓ Advertising as: 'FileTransfer'
✓ Service UUID: 12345678-1234-5678-1234-56789abcdef0
✓ Upload directory: /path/to/uploads
============================================================

Waiting for connections... (Press Ctrl+C to stop)
```

### Using the Web Client

1. Serve the HTML file over HTTPS or localhost:

**Option A - Simple Python HTTP Server (localhost):**
```bash
python3 -m http.server 8000
```
Then open: `http://localhost:8000/client.html`

**Option B - Using HTTPS (required for non-localhost):**
Use a web server with SSL certificate (nginx, Apache, etc.)

2. Open the client page in a compatible browser

3. Click "Connect to Server"

4. Select "FileTransfer" from the Bluetooth device list

5. Choose a file to upload

6. Click "Upload File"

7. Monitor progress in the UI and activity log

### File Transfer Process

The client automatically handles:
- ✅ File chunking (512 bytes per chunk)
- ✅ Progress tracking
- ✅ Retry logic for failed chunks
- ✅ Status verification after upload

The server automatically:
- ✅ Receives and buffers file chunks
- ✅ Prevents directory traversal attacks
- ✅ Creates upload directory if needed
- ✅ Saves files with original names

## Security Considerations

1. **Directory Traversal Protection:** The server validates file paths to prevent writing outside the upload directory

2. **File Size Limits:** BLE has inherent bandwidth limitations; very large files will take time to transfer

3. **Authentication:** This implementation does not include authentication. For production use, implement proper authentication mechanisms

4. **Network Security:** The web client requires HTTPS (except on localhost) per Web Bluetooth API requirements

## Troubleshooting

### Server Issues

**"No Bluetooth adapter found"**
```bash
# Check if adapter is available
hciconfig -a
# or
bluetoothctl list
```

**"Failed to register application: Permission denied"**
```bash
# Run with sudo or ensure user is in bluetooth group
sudo usermod -a -G bluetooth $USER
# Log out and back in
```

**"Bluetooth service is not active"**
```bash
sudo systemctl start bluetooth
sudo systemctl status bluetooth
```

### Client Issues

**"Web Bluetooth API is not available"**
- Use Chrome, Edge, or Opera browser
- Access via HTTPS or localhost
- Check if browser flag is enabled: `chrome://flags/#enable-web-bluetooth`

**"GATT operation failed"**
- Connection lost - try reconnecting
- Move devices closer together
- Reduce interference from other Bluetooth devices

**"Server reported an error"**
- Check server console for detailed error messages
- Verify upload directory permissions
- Check available disk space

## File Size Recommendations

Due to BLE bandwidth limitations:
- ✅ Small files (< 1 MB): Fast and reliable
- ⚠️ Medium files (1-10 MB): May take several minutes
- ❌ Large files (> 10 MB): Not recommended, consider alternative methods

Transfer speed: ~1-5 KB/s (typical BLE throughput with this implementation)

## Technical Details

### Maximum Transmission Unit (MTU)

BLE GATT has MTU limitations:
- Default MTU: 23 bytes (20 bytes payload)
- Extended MTU: Up to 512 bytes
- This implementation uses 512-byte chunks with `writeValueWithoutResponse`

### D-Bus Interface

The server uses the BlueZ D-Bus API:
- `org.bluez.GattManager1` - GATT service management
- `org.bluez.GattService1` - Service definition
- `org.bluez.GattCharacteristic1` - Characteristic implementation
- `org.bluez.LEAdvertisingManager1` - Advertisement management

### Web Bluetooth API

The client uses standard Web Bluetooth API:
- `navigator.bluetooth.requestDevice()` - Device selection
- `device.gatt.connect()` - GATT connection
- `service.getCharacteristic()` - Characteristic access
- `characteristic.writeValue()` - Data transfer

## Development

### Modifying UUIDs

To use custom UUIDs, update both files:

**bluetooth_server.py:**
```python
FILE_TRANSFER_SERVICE_UUID = 'your-service-uuid'
FILE_DATA_CHAR_UUID = 'your-data-characteristic-uuid'
FILE_NAME_CHAR_UUID = 'your-name-characteristic-uuid'
FILE_CONTROL_CHAR_UUID = 'your-control-characteristic-uuid'
```

**client.js:**
```javascript
const FILE_TRANSFER_SERVICE_UUID = 'your-service-uuid';
const FILE_DATA_CHAR_UUID = 'your-data-characteristic-uuid';
const FILE_NAME_CHAR_UUID = 'your-name-characteristic-uuid';
const FILE_CONTROL_CHAR_UUID = 'your-control-characteristic-uuid';
```

### Adjusting Chunk Size

Modify in **client.js:**
```javascript
const CHUNK_SIZE = 512; // Maximum safe value for most BLE devices
```

Smaller values may improve reliability but reduce throughput.

## License

This project is part of the Web-Bluetooth-Data-Exfiltration repository.

## Contributing

Contributions are welcome! Please ensure:
- Code follows existing style
- Dependencies are documented
- Security implications are considered

## References

- [Web Bluetooth API Specification](https://webbluetoothcg.github.io/web-bluetooth/)
- [BlueZ D-Bus GATT API](https://git.kernel.org/pub/scm/bluetooth/bluez.git/tree/doc/gatt-api.txt)
- [Bluetooth GATT Specifications](https://www.bluetooth.com/specifications/gatt/)

## Support

For issues and questions:
1. Check the Troubleshooting section
2. Review server console output
3. Check browser console for client errors
4. Open an issue on GitHub with detailed logs

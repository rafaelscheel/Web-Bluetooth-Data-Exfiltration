# File Transfer Protocol Example

This document demonstrates the Web Bluetooth file transfer protocol flow.

## Protocol Flow

```
Client                                  Server
------                                  ------

1. Connect to GATT Server
   requestDevice() ─────────────────> [Advertising]
   connect() ───────────────────────> [Accept Connection]

2. Discover Service & Characteristics
   getPrimaryService() ──────────────> [File Transfer Service]
   getCharacteristic() (x3) ─────────> [3 Characteristics]

3. Set File Name
   Write "example.txt" ──────────────> [File Name Char]
                                       └─> file_name = "example.txt"

4. Start Transfer
   Write "START" ────────────────────> [Control Char]
                                       └─> Clear buffer
                                       └─> Status = "STARTED"

5. Transfer File Data (chunked)
   Write chunk[0] (512 bytes) ───────> [Data Char]
                                       └─> Append to buffer
   Write chunk[1] (512 bytes) ───────> [Data Char]
                                       └─> Append to buffer
   ...
   Write chunk[N] (remaining bytes) ─> [Data Char]
                                       └─> Append to buffer

6. End Transfer
   Write "END" ──────────────────────> [Control Char]
                                       └─> Save buffer to file
                                       └─> uploads/example.txt
                                       └─> Status = "SAVED"

7. Verify Status
   Read Status <────────────────────── [Control Char]
   Receives "SAVED"
```

## Example: Uploading a 1500-byte file

```
File: test.txt (1500 bytes)
Chunks: ceil(1500 / 512) = 3 chunks

Chunk 0: bytes 0-511    (512 bytes)
Chunk 1: bytes 512-1023 (512 bytes)  
Chunk 2: bytes 1024-1499 (476 bytes)

Timeline:
0ms:    Connect to device
100ms:  Write file name: "test.txt"
200ms:  Write control: "START"
300ms:  Write chunk 0 (512 bytes)
310ms:  Write chunk 1 (512 bytes)
320ms:  Write chunk 2 (476 bytes)
330ms:  Write control: "END"
540ms:  Read control status: "SAVED"
```

## Error Handling

### If transfer fails mid-way:

```
Client                                  Server
------                                  ------

[Transfer in progress...]
                                       [Error occurs]
Write "CANCEL" ───────────────────────> [Control Char]
                                       └─> Clear buffer
                                       └─> Status = "CANCELLED"
```

### If no file name is set:

```
Client                                  Server
------                                  ------

Write "END" ──────────────────────────> [Control Char]
                                       └─> Error: No file name
                                       └─> Status = "ERROR"

Read Status <─────────────────────────[Control Char]
Receives "ERROR"
```

## Characteristics Details

### File Name Characteristic
- **UUID:** `12345678-1234-5678-1234-56789abcdef2`
- **Properties:** Read, Write
- **Format:** UTF-8 encoded string
- **Example:** `"document.pdf"` → `[0x64, 0x6F, 0x63, 0x75, 0x6D, 0x65, 0x6E, 0x74, 0x2E, 0x70, 0x64, 0x66]`

### File Data Characteristic
- **UUID:** `12345678-1234-5678-1234-56789abcdef1`
- **Properties:** Write, Write Without Response
- **Format:** Raw bytes
- **Max Size:** 512 bytes per write
- **Example:** `chunk[0:512]` → Raw binary data

### File Control Characteristic
- **UUID:** `12345678-1234-5678-1234-56789abcdef3`
- **Properties:** Read, Write
- **Format:** UTF-8 encoded command/status string
- **Commands (Write):**
  - `"START"` - Begin transfer
  - `"END"` - Complete transfer and save
  - `"CANCEL"` - Abort transfer
- **Status (Read):**
  - `"READY"` - Initial state
  - `"STARTED"` - Transfer in progress
  - `"SAVED"` - File saved successfully
  - `"ERROR"` - Error occurred
  - `"CANCELLED"` - Transfer cancelled

## JavaScript Code Example

```javascript
// Connect
const device = await navigator.bluetooth.requestDevice({
  filters: [{ services: ['12345678-1234-5678-1234-56789abcdef0'] }]
});
const server = await device.gatt.connect();
const service = await server.getPrimaryService('12345678-1234-5678-1234-56789abcdef0');

// Get characteristics
const nameChar = await service.getCharacteristic('12345678-1234-5678-1234-56789abcdef2');
const dataChar = await service.getCharacteristic('12345678-1234-5678-1234-56789abcdef1');
const ctrlChar = await service.getCharacteristic('12345678-1234-5678-1234-56789abcdef3');

// Upload file
const file = document.getElementById('fileInput').files[0];
const fileName = new TextEncoder().encode(file.name);
await nameChar.writeValue(fileName);

await ctrlChar.writeValue(new TextEncoder().encode('START'));

const data = await file.arrayBuffer();
const chunkSize = 512;
for (let i = 0; i < data.byteLength; i += chunkSize) {
  const chunk = data.slice(i, Math.min(i + chunkSize, data.byteLength));
  await dataChar.writeValueWithoutResponse(chunk);
}

await ctrlChar.writeValue(new TextEncoder().encode('END'));

// Check status
const statusValue = await ctrlChar.readValue();
const status = new TextDecoder().decode(statusValue);
console.log('Status:', status); // "SAVED"
```

## Python Server Code Example

```python
class FileControlCharacteristic(Characteristic):
    def WriteValue(self, value, options):
        global file_buffer, file_name
        
        command = bytes(value).decode('utf-8')
        
        if command == 'START':
            file_buffer = bytearray()
            self.value = b'STARTED'
            
        elif command == 'END':
            if not file_name:
                self.value = b'ERROR'
                return
            
            file_path = os.path.join('uploads', file_name)
            with open(file_path, 'wb') as f:
                f.write(file_buffer)
            
            self.value = b'SAVED'
            file_buffer = bytearray()
            
        elif command == 'CANCEL':
            file_buffer = bytearray()
            self.value = b'CANCELLED'
```

## Timing Considerations

- **Write delay:** ~10ms between chunks (configurable)
- **Retry delay:** 50ms on chunk failure
- **Status check delay:** 200ms after END command
- **Total time:** ~10ms × number_of_chunks + overhead

For a 10 MB file:
- Chunks: 10,000,000 / 512 ≈ 19,531 chunks
- Time: 19,531 × 10ms ≈ 195 seconds (~3.3 minutes)
- Average throughput: ~51 KB/s

## Security Notes

1. **Path Traversal Protection:**
   ```python
   # Server validates file path
   if not os.path.abspath(file_path).startswith(os.path.abspath(upload_directory)):
       # Reject
   ```

2. **File Size:** No explicit limit enforced, but practical BLE limitations apply

3. **File Type:** No filtering - all file types accepted

4. **Overwrite:** Existing files are overwritten without warning

// Web Bluetooth File Upload Client
// Connects to GATT server and uploads files with chunking support

// Service and Characteristic UUIDs (must match server)
const FILE_TRANSFER_SERVICE_UUID = '12345678-1234-5678-1234-56789abcdef0';
const FILE_DATA_CHAR_UUID = '12345678-1234-5678-1234-56789abcdef1';
const FILE_NAME_CHAR_UUID = '12345678-1234-5678-1234-56789abcdef2';
const FILE_CONTROL_CHAR_UUID = '12345678-1234-5678-1234-56789abcdef3';

// Chunk size for file transfer (must be <= 512 bytes for BLE)
// Using 512 bytes as it's the maximum MTU for most BLE devices
const CHUNK_SIZE = 512;

// Global state
let bluetoothDevice = null;
let gattServer = null;
let fileDataCharacteristic = null;
let fileNameCharacteristic = null;
let fileControlCharacteristic = null;
let selectedFile = null;

// DOM elements
const connectBtn = document.getElementById('connectBtn');
const disconnectBtn = document.getElementById('disconnectBtn');
const fileInput = document.getElementById('fileInput');
const uploadBtn = document.getElementById('uploadBtn');
const statusDiv = document.getElementById('status');
const statusText = document.getElementById('statusText');
const fileInfo = document.getElementById('fileInfo');
const fileName = document.getElementById('fileName');
const fileSize = document.getElementById('fileSize');
const fileType = document.getElementById('fileType');
const progressContainer = document.getElementById('progressContainer');
const progressFill = document.getElementById('progressFill');
const logEntries = document.getElementById('logEntries');

// Event listeners
connectBtn.addEventListener('click', connectToDevice);
disconnectBtn.addEventListener('click', disconnectDevice);
fileInput.addEventListener('change', handleFileSelect);
uploadBtn.addEventListener('click', uploadFile);

// Utility functions
function log(message, type = 'info') {
    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;
    const timestamp = new Date().toLocaleTimeString();
    entry.textContent = `[${timestamp}] ${message}`;
    logEntries.appendChild(entry);
    logEntries.scrollTop = logEntries.scrollHeight;
    console.log(`[${type.toUpperCase()}] ${message}`);
}

function updateStatus(status) {
    statusDiv.className = `status ${status}`;
    
    switch(status) {
        case 'disconnected':
            statusText.textContent = 'Disconnected';
            connectBtn.disabled = false;
            disconnectBtn.disabled = true;
            fileInput.disabled = true;
            uploadBtn.disabled = true;
            break;
        case 'connecting':
            statusText.textContent = 'Connecting...';
            connectBtn.disabled = true;
            disconnectBtn.disabled = true;
            break;
        case 'connected':
            statusText.textContent = 'Connected';
            connectBtn.disabled = true;
            disconnectBtn.disabled = false;
            fileInput.disabled = false;
            uploadBtn.disabled = !selectedFile;
            break;
    }
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
}

function updateProgress(percent) {
    progressFill.style.width = percent + '%';
    progressFill.textContent = Math.round(percent) + '%';
}

// Bluetooth connection functions
async function connectToDevice() {
    try {
        log('Requesting Bluetooth device...');
        updateStatus('connecting');

        // Request device with our service UUID
        bluetoothDevice = await navigator.bluetooth.requestDevice({
            filters: [{
                services: [FILE_TRANSFER_SERVICE_UUID]
            }],
            optionalServices: [FILE_TRANSFER_SERVICE_UUID]
        });

        log(`Selected device: ${bluetoothDevice.name}`);
        
        // Set up disconnect handler
        bluetoothDevice.addEventListener('gattserverdisconnected', onDisconnected);

        // Connect to GATT server
        log('Connecting to GATT server...');
        gattServer = await bluetoothDevice.gatt.connect();
        log('Connected to GATT server', 'success');

        // Get the file transfer service
        log('Getting File Transfer service...');
        const service = await gattServer.getPrimaryService(FILE_TRANSFER_SERVICE_UUID);
        log('Got File Transfer service', 'success');

        // Get characteristics
        log('Getting characteristics...');
        fileNameCharacteristic = await service.getCharacteristic(FILE_NAME_CHAR_UUID);
        fileDataCharacteristic = await service.getCharacteristic(FILE_DATA_CHAR_UUID);
        fileControlCharacteristic = await service.getCharacteristic(FILE_CONTROL_CHAR_UUID);
        log('Got all characteristics', 'success');

        updateStatus('connected');
        log('✓ Ready to upload files!', 'success');

    } catch (error) {
        log(`Error: ${error.message}`, 'error');
        updateStatus('disconnected');
        cleanupConnection();
    }
}

function onDisconnected() {
    log('Device disconnected', 'error');
    updateStatus('disconnected');
    cleanupConnection();
}

async function disconnectDevice() {
    if (bluetoothDevice && bluetoothDevice.gatt.connected) {
        log('Disconnecting...');
        bluetoothDevice.gatt.disconnect();
    }
    cleanupConnection();
    updateStatus('disconnected');
}

function cleanupConnection() {
    gattServer = null;
    fileDataCharacteristic = null;
    fileNameCharacteristic = null;
    fileControlCharacteristic = null;
}

// File handling functions
function handleFileSelect(event) {
    const file = event.target.files[0];
    if (!file) {
        selectedFile = null;
        fileInfo.style.display = 'none';
        uploadBtn.disabled = true;
        return;
    }

    selectedFile = file;
    fileName.textContent = file.name;
    fileSize.textContent = formatBytes(file.size);
    fileType.textContent = file.type || 'unknown';
    fileInfo.style.display = 'block';
    uploadBtn.disabled = !gattServer;
    
    log(`File selected: ${file.name} (${formatBytes(file.size)})`);
}

async function uploadFile() {
    if (!selectedFile || !gattServer) {
        log('No file selected or not connected', 'error');
        return;
    }

    try {
        uploadBtn.disabled = true;
        progressContainer.classList.add('active');
        updateProgress(0);

        log(`Starting upload: ${selectedFile.name}`);

        // Step 1: Write file name
        log('Writing file name...');
        const nameEncoder = new TextEncoder();
        const nameBytes = nameEncoder.encode(selectedFile.name);
        await fileNameCharacteristic.writeValue(nameBytes);
        log('File name written', 'success');

        // Step 2: Send START command
        log('Sending START command...');
        const startEncoder = new TextEncoder();
        const startBytes = startEncoder.encode('START');
        await fileControlCharacteristic.writeValue(startBytes);
        log('START command sent', 'success');

        // Small delay to ensure server is ready
        await new Promise(resolve => setTimeout(resolve, 100));

        // Step 3: Read file and send in chunks
        log(`Sending file data in ${CHUNK_SIZE}-byte chunks...`);
        const fileData = await selectedFile.arrayBuffer();
        const totalChunks = Math.ceil(fileData.byteLength / CHUNK_SIZE);
        
        log(`Total file size: ${formatBytes(fileData.byteLength)}`);
        log(`Total chunks: ${totalChunks}`);

        for (let i = 0; i < totalChunks; i++) {
            const start = i * CHUNK_SIZE;
            const end = Math.min(start + CHUNK_SIZE, fileData.byteLength);
            const chunk = fileData.slice(start, end);
            
            // Write chunk with retry logic
            let retries = 3;
            let success = false;
            
            while (retries > 0 && !success) {
                try {
                    await fileDataCharacteristic.writeValueWithoutResponse(chunk);
                    success = true;
                } catch (error) {
                    retries--;
                    if (retries === 0) {
                        throw error;
                    }
                    log(`Chunk ${i + 1} failed (${error.message}), retrying... (${retries} attempts left)`, 'error');
                    await new Promise(resolve => setTimeout(resolve, 50));
                }
            }
            
            // Update progress
            const progress = ((i + 1) / totalChunks) * 100;
            updateProgress(progress);
            
            if ((i + 1) % 10 === 0 || i === totalChunks - 1) {
                log(`Sent ${i + 1}/${totalChunks} chunks (${Math.round(progress)}%)`);
            }

            // Small delay between chunks to avoid overwhelming the server
            if (i < totalChunks - 1) {
                await new Promise(resolve => setTimeout(resolve, 10));
            }
        }

        log('All chunks sent', 'success');

        // Step 4: Send END command to finalize
        log('Sending END command...');
        const endEncoder = new TextEncoder();
        const endBytes = endEncoder.encode('END');
        await fileControlCharacteristic.writeValue(endBytes);
        
        // Wait a bit for the server to process
        await new Promise(resolve => setTimeout(resolve, 200));

        // Read the control characteristic to check status
        const statusValue = await fileControlCharacteristic.readValue();
        const statusDecoder = new TextDecoder();
        const status = statusDecoder.decode(statusValue);
        
        if (status.includes('SAVED')) {
            log('✓ File upload completed successfully!', 'success');
            log(`✓ File saved on server: ${selectedFile.name}`, 'success');
        } else if (status.includes('ERROR')) {
            throw new Error('Server reported an error while saving the file');
        } else {
            log(`Server status: ${status}`);
        }

        // Reset UI
        updateProgress(100);
        setTimeout(() => {
            progressContainer.classList.remove('active');
            updateProgress(0);
            uploadBtn.disabled = false;
        }, 2000);

    } catch (error) {
        log(`Upload failed: ${error.message}`, 'error');
        progressContainer.classList.remove('active');
        updateProgress(0);
        uploadBtn.disabled = false;

        // Try to send CANCEL command
        try {
            if (fileControlCharacteristic) {
                const cancelEncoder = new TextEncoder();
                const cancelBytes = cancelEncoder.encode('CANCEL');
                await fileControlCharacteristic.writeValue(cancelBytes);
                log('Sent CANCEL command', 'error');
            }
        } catch (cancelError) {
            log('Could not send CANCEL command', 'error');
        }
    }
}

// Check browser compatibility on load
window.addEventListener('load', () => {
    if (!navigator.bluetooth) {
        log('Web Bluetooth API is not available in this browser!', 'error');
        log('Please use Chrome, Edge, or Opera with HTTPS or localhost', 'error');
        connectBtn.disabled = true;
        connectBtn.textContent = 'Web Bluetooth Not Supported';
    } else {
        log('Web Bluetooth API is available', 'success');
        log('Click "Connect to Server" to begin');
    }
});

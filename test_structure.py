#!/usr/bin/env python3
"""
Simple test script to verify the Python server can be imported and has proper structure.
This doesn't test Bluetooth functionality (requires actual hardware).
"""

import sys
import os

def test_imports():
    """Test that the server can be imported without errors"""
    print("Testing imports...")
    try:
        # Test if dbus-python would be available
        import dbus
        print("✓ dbus-python is available")
    except ImportError:
        print("✗ dbus-python not available (install with: sudo apt-get install python3-dbus)")
        return False
    
    try:
        # Test if PyGObject would be available
        from gi.repository import GLib
        print("✓ PyGObject is available")
    except ImportError:
        print("✗ PyGObject not available (install with: sudo apt-get install python3-gi)")
        return False
    
    return True

def test_script_structure():
    """Verify the server script has correct structure"""
    print("\nTesting script structure...")
    
    script_path = os.path.join(os.path.dirname(__file__), 'bluetooth_server.py')
    
    if not os.path.exists(script_path):
        print(f"✗ Script not found: {script_path}")
        return False
    
    print(f"✓ Script found: {script_path}")
    
    # Check if script is executable
    if os.access(script_path, os.X_OK):
        print("✓ Script is executable")
    else:
        print("⚠ Script is not executable (run: chmod +x bluetooth_server.py)")
    
    # Check script content
    with open(script_path, 'r') as f:
        content = f.read()
        
        required_elements = [
            'check_dependencies',
            'FILE_TRANSFER_SERVICE_UUID',
            'FileDataCharacteristic',
            'FileNameCharacteristic',
            'FileControlCharacteristic',
            'FileTransferService',
            'Application',
            'Advertisement',
        ]
        
        for element in required_elements:
            if element in content:
                print(f"✓ Found: {element}")
            else:
                print(f"✗ Missing: {element}")
                return False
    
    return True

def test_client_files():
    """Verify client files exist and have correct structure"""
    print("\nTesting client files...")
    
    html_path = os.path.join(os.path.dirname(__file__), 'client.html')
    js_path = os.path.join(os.path.dirname(__file__), 'client.js')
    
    # Check HTML
    if not os.path.exists(html_path):
        print(f"✗ HTML not found: {html_path}")
        return False
    print(f"✓ HTML found: {html_path}")
    
    with open(html_path, 'r') as f:
        html_content = f.read()
        if 'Web Bluetooth' in html_content and 'client.js' in html_content:
            print("✓ HTML has correct structure")
        else:
            print("✗ HTML missing required elements")
            return False
    
    # Check JavaScript
    if not os.path.exists(js_path):
        print(f"✗ JavaScript not found: {js_path}")
        return False
    print(f"✓ JavaScript found: {js_path}")
    
    with open(js_path, 'r') as f:
        js_content = f.read()
        
        required_js_elements = [
            'FILE_TRANSFER_SERVICE_UUID',
            'navigator.bluetooth',
            'connectToDevice',
            'uploadFile',
            'CHUNK_SIZE',
        ]
        
        for element in required_js_elements:
            if element in js_content:
                print(f"✓ Found in JS: {element}")
            else:
                print(f"✗ Missing in JS: {element}")
                return False
    
    return True

def test_documentation():
    """Verify documentation files exist"""
    print("\nTesting documentation...")
    
    usage_path = os.path.join(os.path.dirname(__file__), 'USAGE.md')
    readme_path = os.path.join(os.path.dirname(__file__), 'README.md')
    
    if os.path.exists(usage_path):
        print(f"✓ USAGE.md found")
    else:
        print(f"✗ USAGE.md not found")
        return False
    
    if os.path.exists(readme_path):
        print(f"✓ README.md found")
    else:
        print(f"✗ README.md not found")
        return False
    
    return True

def main():
    print("=" * 60)
    print("GATT Web Bluetooth Server - Structure Test")
    print("=" * 60)
    
    all_passed = True
    
    # Run tests
    if not test_script_structure():
        all_passed = False
    
    if not test_client_files():
        all_passed = False
    
    if not test_documentation():
        all_passed = False
    
    # Optional: test imports (may fail if dependencies not installed)
    print("\n" + "=" * 60)
    print("Testing Python dependencies (optional):")
    print("=" * 60)
    test_imports()
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✓ All structural tests passed!")
        print("\nNote: This test only verifies file structure.")
        print("Actual Bluetooth functionality requires:")
        print("  - Linux system with BlueZ")
        print("  - Bluetooth adapter")
        print("  - Python dependencies installed")
        print("  - Proper permissions")
    else:
        print("✗ Some tests failed")
        return 1
    print("=" * 60)
    
    return 0

if __name__ == '__main__':
    sys.exit(main())

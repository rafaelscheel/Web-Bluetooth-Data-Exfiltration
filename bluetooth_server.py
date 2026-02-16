#!/usr/bin/env python3
"""
GATT Web Bluetooth Server for File Upload
Uses BlueZ, D-Bus to create a GATT server that receives files from Web Bluetooth clients.
"""

import sys
import os
import dbus
import dbus.exceptions
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib
import array
import subprocess

# BlueZ D-Bus paths
BLUEZ_SERVICE_NAME = 'org.bluez'
GATT_MANAGER_IFACE = 'org.bluez.GattManager1'
DBUS_OM_IFACE = 'org.freedesktop.DBus.ObjectManager'
DBUS_PROP_IFACE = 'org.freedesktop.DBus.Properties'
GATT_SERVICE_IFACE = 'org.bluez.GattService1'
GATT_CHRC_IFACE = 'org.bluez.GattCharacteristic1'
GATT_DESC_IFACE = 'org.bluez.GattDescriptor1'
LE_ADVERTISING_MANAGER_IFACE = 'org.bluez.LEAdvertisingManager1'
LE_ADVERTISEMENT_IFACE = 'org.bluez.LEAdvertisement1'

# UUIDs for our custom service
FILE_TRANSFER_SERVICE_UUID = '12345678-1234-5678-1234-56789abcdef0'
FILE_DATA_CHAR_UUID = '12345678-1234-5678-1234-56789abcdef1'
FILE_NAME_CHAR_UUID = '12345678-1234-5678-1234-56789abcdef2'
FILE_CONTROL_CHAR_UUID = '12345678-1234-5678-1234-56789abcdef3'

# Global file buffer
file_buffer = bytearray()
file_name = ""
upload_directory = "./uploads"


def check_dependencies():
    """Check for required dependencies and services."""
    print("Checking dependencies...")
    issues = []
    
    # Check if BlueZ is installed
    try:
        result = subprocess.run(['bluetoothctl', '--version'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print(f"✓ BlueZ installed: {result.stdout.strip()}")
        else:
            issues.append("BlueZ (bluetoothctl) not found")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        issues.append("BlueZ (bluetoothctl) not found")
    
    # Check if bluetooth service is running
    try:
        result = subprocess.run(['systemctl', 'is-active', 'bluetooth'], 
                              capture_output=True, text=True, timeout=5)
        if result.stdout.strip() == 'active':
            print("✓ Bluetooth service is active")
        else:
            issues.append("Bluetooth service is not active")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("⚠ Could not check bluetooth service status (systemctl not available)")
    
    # Check if D-Bus is available
    try:
        dbus.SystemBus()
        print("✓ D-Bus system bus is available")
    except dbus.exceptions.DBusException as e:
        issues.append(f"D-Bus system bus not available: {e}")
    
    # Check for bluetooth adapters
    try:
        bus = dbus.SystemBus()
        manager = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, '/'),
                                DBUS_OM_IFACE)
        objects = manager.GetManagedObjects()
        
        adapters = []
        for path, interfaces in objects.items():
            if 'org.bluez.Adapter1' in interfaces:
                adapters.append(path)
        
        if adapters:
            print(f"✓ Found {len(adapters)} Bluetooth adapter(s):")
            for adapter in adapters:
                print(f"  - {adapter}")
        else:
            issues.append("No Bluetooth adapters found")
    except dbus.exceptions.DBusException as e:
        issues.append(f"Could not check for Bluetooth adapters: {e}")
    
    if issues:
        print("\n❌ Issues found:")
        for issue in issues:
            print(f"  - {issue}")
        print("\nRecommendations:")
        print("  1. Install BlueZ: sudo apt-get install bluez")
        print("  2. Start bluetooth service: sudo systemctl start bluetooth")
        print("  3. Enable bluetooth service: sudo systemctl enable bluetooth")
        print("  4. Check if bluetooth adapter is enabled: bluetoothctl show")
        print("  5. Ensure user is in 'bluetooth' group: sudo usermod -a -G bluetooth $USER")
        return False
    
    print("\n✓ All dependencies satisfied!")
    return True


class InvalidArgsException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.freedesktop.DBus.Error.InvalidArgs'


class NotSupportedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.NotSupported'


class NotPermittedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.NotPermitted'


class InvalidValueLengthException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.InvalidValueLength'


class FailedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.Failed'


class Application(dbus.service.Object):
    """
    org.bluez.GattApplication1 interface implementation
    """
    def __init__(self, bus):
        self.path = '/'
        self.services = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_service(self, service):
        self.services.append(service)

    @dbus.service.method('org.freedesktop.DBus.ObjectManager',
                         out_signature='a{oa{sa{sv}}}')
    def GetManagedObjects(self):
        response = {}
        for service in self.services:
            response[service.get_path()] = service.get_properties()
            chrcs = service.get_characteristics()
            for chrc in chrcs:
                response[chrc.get_path()] = chrc.get_properties()
                descs = chrc.get_descriptors()
                for desc in descs:
                    response[desc.get_path()] = desc.get_properties()
        return response


class Service(dbus.service.Object):
    """
    org.bluez.GattService1 interface implementation
    """
    PATH_BASE = '/org/bluez/example/service'

    def __init__(self, bus, index, uuid, primary):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.uuid = uuid
        self.primary = primary
        self.characteristics = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_SERVICE_IFACE: {
                'UUID': self.uuid,
                'Primary': self.primary,
                'Characteristics': dbus.Array(
                    self.get_characteristic_paths(),
                    signature='o')
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_characteristic(self, characteristic):
        self.characteristics.append(characteristic)

    def get_characteristic_paths(self):
        result = []
        for chrc in self.characteristics:
            result.append(chrc.get_path())
        return result

    def get_characteristics(self):
        return self.characteristics

    @dbus.service.method('org.freedesktop.DBus.Properties',
                         in_signature='s',
                         out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_SERVICE_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[GATT_SERVICE_IFACE]


class Characteristic(dbus.service.Object):
    """
    org.bluez.GattCharacteristic1 interface implementation
    """
    def __init__(self, bus, index, uuid, flags, service):
        self.path = service.path + '/char' + str(index)
        self.bus = bus
        self.uuid = uuid
        self.service = service
        self.flags = flags
        self.descriptors = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_CHRC_IFACE: {
                'Service': self.service.get_path(),
                'UUID': self.uuid,
                'Flags': self.flags,
                'Descriptors': dbus.Array(
                    self.get_descriptor_paths(),
                    signature='o')
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_descriptor(self, descriptor):
        self.descriptors.append(descriptor)

    def get_descriptor_paths(self):
        result = []
        for desc in self.descriptors:
            result.append(desc.get_path())
        return result

    def get_descriptors(self):
        return self.descriptors

    @dbus.service.method('org.freedesktop.DBus.Properties',
                         in_signature='s',
                         out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_CHRC_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[GATT_CHRC_IFACE]

    @dbus.service.method(GATT_CHRC_IFACE,
                        in_signature='a{sv}',
                        out_signature='ay')
    def ReadValue(self, options):
        print('Default ReadValue called, returning error')
        raise NotSupportedException()

    @dbus.service.method(GATT_CHRC_IFACE, in_signature='aya{sv}')
    def WriteValue(self, value, options):
        print('Default WriteValue called, returning error')
        raise NotSupportedException()

    @dbus.service.method(GATT_CHRC_IFACE)
    def StartNotify(self):
        print('Default StartNotify called, returning error')
        raise NotSupportedException()

    @dbus.service.method(GATT_CHRC_IFACE)
    def StopNotify(self):
        print('Default StopNotify called, returning error')
        raise NotSupportedException()

    @dbus.service.signal(DBUS_PROP_IFACE,
                         signature='sa{sv}as')
    def PropertiesChanged(self, interface, changed, invalidated):
        pass


class Descriptor(dbus.service.Object):
    """
    org.bluez.GattDescriptor1 interface implementation
    """
    def __init__(self, bus, index, uuid, flags, characteristic):
        self.path = characteristic.path + '/desc' + str(index)
        self.bus = bus
        self.uuid = uuid
        self.flags = flags
        self.chrc = characteristic
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_DESC_IFACE: {
                'Characteristic': self.chrc.get_path(),
                'UUID': self.uuid,
                'Flags': self.flags,
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method('org.freedesktop.DBus.Properties',
                         in_signature='s',
                         out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_DESC_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[GATT_DESC_IFACE]

    @dbus.service.method(GATT_DESC_IFACE,
                        in_signature='a{sv}',
                        out_signature='ay')
    def ReadValue(self, options):
        print('Default ReadValue called, returning error')
        raise NotSupportedException()

    @dbus.service.method(GATT_DESC_IFACE, in_signature='aya{sv}')
    def WriteValue(self, value, options):
        print('Default WriteValue called, returning error')
        raise NotSupportedException()


class FileDataCharacteristic(Characteristic):
    """
    Characteristic for receiving file data chunks
    """
    def __init__(self, bus, index, service):
        Characteristic.__init__(
            self, bus, index,
            FILE_DATA_CHAR_UUID,
            ['write', 'write-without-response'],
            service)

    def WriteValue(self, value, options):
        global file_buffer
        
        # Convert dbus.Array to bytes
        data = bytes(value)
        file_buffer.extend(data)
        
        print(f'Received {len(data)} bytes, total: {len(file_buffer)} bytes')


class FileNameCharacteristic(Characteristic):
    """
    Characteristic for receiving file name
    """
    def __init__(self, bus, index, service):
        Characteristic.__init__(
            self, bus, index,
            FILE_NAME_CHAR_UUID,
            ['write', 'read'],
            service)
        self.value = []

    def ReadValue(self, options):
        return self.value

    def WriteValue(self, value, options):
        global file_name
        
        # Convert dbus.Array to string
        file_name = bytes(value).decode('utf-8')
        self.value = value
        
        print(f'File name set to: {file_name}')


class FileControlCharacteristic(Characteristic):
    """
    Characteristic for file transfer control (start, end, cancel)
    Commands:
    - 'START' - Start file transfer
    - 'END' - End file transfer and save file
    - 'CANCEL' - Cancel file transfer
    """
    def __init__(self, bus, index, service):
        Characteristic.__init__(
            self, bus, index,
            FILE_CONTROL_CHAR_UUID,
            ['write', 'read'],
            service)
        self.value = [ord('R'), ord('E'), ord('A'), ord('D'), ord('Y')]

    def ReadValue(self, options):
        return self.value

    def WriteValue(self, value, options):
        global file_buffer, file_name, upload_directory
        
        # Convert dbus.Array to string
        command = bytes(value).decode('utf-8')
        
        print(f'Control command received: {command}')
        
        if command == 'START':
            file_buffer = bytearray()
            print('File transfer started, buffer cleared')
            self.value = [ord('S'), ord('T'), ord('A'), ord('R'), ord('T'), ord('E'), ord('D')]
            
        elif command == 'END':
            if not file_name:
                print('Error: No file name set')
                self.value = [ord('E'), ord('R'), ord('R'), ord('O'), ord('R')]
                return
            
            # Create upload directory if it doesn't exist
            os.makedirs(upload_directory, exist_ok=True)
            
            # Save the file
            file_path = os.path.join(upload_directory, file_name)
            
            # Prevent directory traversal
            if not os.path.abspath(file_path).startswith(os.path.abspath(upload_directory)):
                print(f'Error: Invalid file path (directory traversal attempt)')
                self.value = [ord('E'), ord('R'), ord('R'), ord('O'), ord('R')]
                return
            
            try:
                with open(file_path, 'wb') as f:
                    f.write(file_buffer)
                
                print(f'File saved: {file_path} ({len(file_buffer)} bytes)')
                self.value = [ord('S'), ord('A'), ord('V'), ord('E'), ord('D')]
                
                # Clear buffer after saving
                file_buffer = bytearray()
                
            except Exception as e:
                print(f'Error saving file: {e}')
                self.value = [ord('E'), ord('R'), ord('R'), ord('O'), ord('R')]
                
        elif command == 'CANCEL':
            file_buffer = bytearray()
            print('File transfer cancelled')
            self.value = [ord('C'), ord('A'), ord('N'), ord('C'), ord('E'), ord('L'), ord('L'), ord('E'), ord('D')]
        
        else:
            print(f'Unknown command: {command}')


class FileTransferService(Service):
    """
    File Transfer GATT Service
    """
    def __init__(self, bus, index):
        Service.__init__(self, bus, index, FILE_TRANSFER_SERVICE_UUID, True)
        self.add_characteristic(FileNameCharacteristic(bus, 0, self))
        self.add_characteristic(FileDataCharacteristic(bus, 1, self))
        self.add_characteristic(FileControlCharacteristic(bus, 2, self))


class Advertisement(dbus.service.Object):
    """
    org.bluez.LEAdvertisement1 interface implementation
    """
    PATH_BASE = '/org/bluez/example/advertisement'

    def __init__(self, bus, index, advertising_type):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.ad_type = advertising_type
        self.service_uuids = None
        self.manufacturer_data = None
        self.solicit_uuids = None
        self.service_data = None
        self.local_name = None
        self.include_tx_power = False
        self.includes = None
        self.data = None
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        properties = dict()
        properties['Type'] = self.ad_type
        if self.service_uuids is not None:
            properties['ServiceUUIDs'] = dbus.Array(self.service_uuids,
                                                    signature='s')
        if self.solicit_uuids is not None:
            properties['SolicitUUIDs'] = dbus.Array(self.solicit_uuids,
                                                    signature='s')
        if self.manufacturer_data is not None:
            properties['ManufacturerData'] = dbus.Dictionary(
                self.manufacturer_data, signature='qv')
        if self.service_data is not None:
            properties['ServiceData'] = dbus.Dictionary(self.service_data,
                                                       signature='sv')
        if self.local_name is not None:
            properties['LocalName'] = dbus.String(self.local_name)
        if self.include_tx_power:
            properties['IncludeTxPower'] = dbus.Boolean(self.include_tx_power)
        if self.includes is not None:
            properties['Includes'] = dbus.Array(self.includes, signature='s')

        if self.data is not None:
            properties['Data'] = dbus.Dictionary(
                self.data, signature='yv')
        return {LE_ADVERTISEMENT_IFACE: properties}

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_service_uuid(self, uuid):
        if not self.service_uuids:
            self.service_uuids = []
        self.service_uuids.append(uuid)

    def add_solicit_uuid(self, uuid):
        if not self.solicit_uuids:
            self.solicit_uuids = []
        self.solicit_uuids.append(uuid)

    def add_manufacturer_data(self, manuf_code, data):
        if not self.manufacturer_data:
            self.manufacturer_data = dbus.Dictionary({}, signature='qv')
        self.manufacturer_data[manuf_code] = dbus.Array(data, signature='y')

    def add_service_data(self, uuid, data):
        if not self.service_data:
            self.service_data = dbus.Dictionary({}, signature='sv')
        self.service_data[uuid] = dbus.Array(data, signature='y')

    def add_local_name(self, name):
        self.local_name = dbus.String(name)

    @dbus.service.method('org.freedesktop.DBus.Properties',
                         in_signature='s',
                         out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != LE_ADVERTISEMENT_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[LE_ADVERTISEMENT_IFACE]

    @dbus.service.method(LE_ADVERTISEMENT_IFACE,
                         in_signature='',
                         out_signature='')
    def Release(self):
        print('%s: Released!' % self.path)


class FileTransferAdvertisement(Advertisement):
    """
    Advertisement for File Transfer Service
    """
    def __init__(self, bus, index):
        Advertisement.__init__(self, bus, index, 'peripheral')
        self.add_service_uuid(FILE_TRANSFER_SERVICE_UUID)
        self.add_local_name('FileTransfer')
        self.include_tx_power = True
        self.includes = ['tx-power']


def register_app_cb():
    print('GATT application registered')


def register_app_error_cb(error):
    print('Failed to register application: ' + str(error))
    mainloop.quit()


def register_ad_cb():
    print('Advertisement registered')


def register_ad_error_cb(error):
    print('Failed to register advertisement: ' + str(error))
    mainloop.quit()


def find_adapter(bus):
    """Find the first available Bluetooth adapter that supports GATT management"""
    remote_om = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, '/'),
                               DBUS_OM_IFACE)
    objects = remote_om.GetManagedObjects()

    for o, props in objects.items():
        if GATT_MANAGER_IFACE in props:
            return o

    return None


def main():
    global mainloop

    print("=" * 60)
    print("GATT Web Bluetooth Server - File Upload Service")
    print("=" * 60)

    # Setup D-Bus main loop before any D-Bus operations (including dependency checks)
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    # Check dependencies first
    if not check_dependencies():
        print("\n❌ Dependency check failed. Please fix the issues above.")
        sys.exit(1)

    print("\nStarting GATT server...")

    bus = dbus.SystemBus()

    # Find adapter
    adapter_path = find_adapter(bus)
    if not adapter_path:
        print('❌ No Bluetooth adapter found')
        sys.exit(1)

    print(f'Using adapter: {adapter_path}')

    # Setup GATT Service Manager
    service_manager = dbus.Interface(
        bus.get_object(BLUEZ_SERVICE_NAME, adapter_path),
        GATT_MANAGER_IFACE)

    # Setup Advertisement Manager
    ad_manager = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, adapter_path),
                                LE_ADVERTISING_MANAGER_IFACE)

    # Create application
    app = Application(bus)
    app.add_service(FileTransferService(bus, 0))

    # Create advertisement
    adv = FileTransferAdvertisement(bus, 0)

    mainloop = GLib.MainLoop()

    print('Registering GATT application...')
    service_manager.RegisterApplication(app.get_path(), {},
                                       reply_handler=register_app_cb,
                                       error_handler=register_app_error_cb)

    print('Registering advertisement...')
    ad_manager.RegisterAdvertisement(adv.get_path(), {},
                                     reply_handler=register_ad_cb,
                                     error_handler=register_ad_error_cb)

    print("\n" + "=" * 60)
    print("✓ Server is running!")
    print(f"✓ Advertising as: 'FileTransfer'")
    print(f"✓ Service UUID: {FILE_TRANSFER_SERVICE_UUID}")
    print(f"✓ Upload directory: {os.path.abspath(upload_directory)}")
    print("=" * 60)
    print("\nWaiting for connections... (Press Ctrl+C to stop)")
    
    try:
        mainloop.run()
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        adv.Release()


if __name__ == '__main__':
    main()

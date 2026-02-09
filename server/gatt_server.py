#!/usr/bin/env python3
"""
GATT Bluetooth Server for file upload via Web Bluetooth.

Uses BlueZ 5.x D-Bus API with dbus-python and PyGObject (GLib main loop).
Registers a custom GATT service with control and data characteristics,
advertises via BLE, and receives chunked file uploads from a Web Bluetooth client.

Protocol:
  1. Client writes to Control Characteristic: 0x01 + UTF-8 filename bytes = BEGIN
  2. Client writes chunks to Data Characteristic (raw file bytes)
  3. Client writes to Control Characteristic: 0x02 = END (finalize and save)
  4. Client writes to Control Characteristic: 0x03 = ABORT (discard transfer)

Requirements:
  - Linux with BlueZ 5.x
  - bluetoothd running in experimental mode (for GATT server support)
  - python3-dbus (dbus-python)
  - python3-gi (PyGObject)
  - A Bluetooth adapter that supports BLE (Bluetooth 4.0+)

Usage:
  sudo python3 gatt_server.py [--adapter hci0] [--upload-dir ./uploads]
"""

import argparse
import os
import sys
import shutil
import subprocess
import tempfile

# ---------------------------------------------------------------------------
# Dependency check — run before importing dbus/gi so we can give clear errors
# ---------------------------------------------------------------------------

def check_dependencies(adapter_name='hci0'):
    """
    Verify that all required system dependencies are present.
    Returns True if everything is OK, or prints recommendations and returns False.
    """
    ok = True

    # 1. Check Python modules
    print('[CHECK] Python module: dbus ...', end=' ')
    try:
        import dbus  # noqa: F401
        print('OK')
    except ImportError:
        print('MISSING')
        print('  -> Install with: sudo apt install python3-dbus')
        ok = False

    print('[CHECK] Python module: gi (PyGObject) ...', end=' ')
    try:
        from gi.repository import GLib  # noqa: F401
        print('OK')
    except ImportError:
        print('MISSING')
        print('  -> Install with: sudo apt install python3-gi gir1.2-glib-2.0')
        ok = False

    # 2. Check bluetoothd is running
    print('[CHECK] bluetoothd service ...', end=' ')
    try:
        result = subprocess.run(
            ['pgrep', '-x', 'bluetoothd'],
            capture_output=True, timeout=5
        )
        if result.returncode == 0:
            print('OK (PID {})'.format(result.stdout.decode().strip().split('\n')[0]))
        else:
            print('NOT RUNNING')
            print('  -> Start with: sudo systemctl start bluetooth')
            print('  -> For GATT server support, bluetoothd must run with --experimental flag.')
            print('     Edit /lib/systemd/system/bluetooth.service and add --experimental to ExecStart,')
            print('     then: sudo systemctl daemon-reload && sudo systemctl restart bluetooth')
            ok = False
    except FileNotFoundError:
        print('UNKNOWN (pgrep not found)')

    # 3. Check bluetoothd experimental mode
    print('[CHECK] bluetoothd --experimental flag ...', end=' ')
    try:
        result = subprocess.run(
            ['ps', '-eo', 'args'],
            capture_output=True, text=True, timeout=5
        )
        bluetoothd_lines = [
            line for line in result.stdout.splitlines()
            if 'bluetoothd' in line and 'ps ' not in line
        ]
        if bluetoothd_lines:
            cmd_line = bluetoothd_lines[0]
            if '--experimental' in cmd_line or '-E' in cmd_line.split():
                print('OK')
            else:
                print('WARNING — --experimental flag not detected')
                print('  -> bluetoothd command: {}'.format(cmd_line.strip()))
                print('  -> GATT server registration may fail without --experimental.')
                print('     Edit /lib/systemd/system/bluetooth.service, add --experimental to ExecStart,')
                print('     then: sudo systemctl daemon-reload && sudo systemctl restart bluetooth')
                # Not fatal — some BlueZ versions enable GATT server without it
        else:
            print('SKIPPED (bluetoothd not found in process list)')
    except Exception as e:
        print('SKIPPED ({})'.format(e))

    # 4. Check for Bluetooth adapter
    print('[CHECK] Bluetooth adapter {} ...'.format(adapter_name), end=' ')
    hci_path = '/sys/class/bluetooth/{}'.format(adapter_name)
    if os.path.exists(hci_path):
        print('OK')
    else:
        print('NOT FOUND')
        print('  -> No adapter at {}. Check with: hciconfig -a'.format(hci_path))
        print('  -> If you have a USB Bluetooth dongle, make sure it is plugged in.')
        print('  -> List available adapters: ls /sys/class/bluetooth/')
        ok = False

    # 5. Check adapter supports LE via D-Bus (only if dbus is available)
    if ok:
        print('[CHECK] Adapter LE support via D-Bus ...', end=' ')
        try:
            import dbus
            bus = dbus.SystemBus()
            adapter_obj = bus.get_object('org.bluez', '/org/bluez/{}'.format(adapter_name))
            props = dbus.Interface(adapter_obj, 'org.freedesktop.DBus.Properties')

            # Check adapter is powered
            powered = props.Get('org.bluez.Adapter1', 'Powered')
            if not powered:
                print('WARNING — adapter is not powered on')
                print('  -> Power on with: sudo bluetoothctl power on')
                print('  -> Or: sudo hciconfig {} up'.format(adapter_name))
                # We will try to power it on later
            else:
                print('OK (powered on)')

            # Check GattManager1 interface exists
            print('[CHECK] GattManager1 interface on adapter ...', end=' ')
            try:
                introspectable = dbus.Interface(
                    adapter_obj, 'org.freedesktop.DBus.Introspectable'
                )
                xml = introspectable.Introspect()
                if 'org.bluez.GattManager1' in xml:
                    print('OK')
                else:
                    print('NOT FOUND')
                    print('  -> BlueZ on this adapter does not expose GattManager1.')
                    print('  -> Ensure bluetoothd runs with --experimental flag.')
                    ok = False
            except Exception as e:
                print('ERROR ({})'.format(e))
                ok = False

            # Check LEAdvertisingManager1 interface exists
            print('[CHECK] LEAdvertisingManager1 interface on adapter ...', end=' ')
            try:
                if 'org.bluez.LEAdvertisingManager1' in xml:
                    print('OK')
                else:
                    print('NOT FOUND')
                    print('  -> BLE advertising not available on this adapter/BlueZ config.')
                    ok = False
            except Exception as e:
                print('ERROR ({})'.format(e))
                ok = False

        except Exception as e:
            print('ERROR ({})'.format(e))
            print('  -> Could not query adapter via D-Bus. Is bluetoothd running?')
            ok = False

    # 6. Check running as root
    print('[CHECK] Running as root ...', end=' ')
    if os.geteuid() == 0:
        print('OK')
    else:
        print('WARNING — not running as root')
        print('  -> BlueZ D-Bus GATT server typically requires root privileges.')
        print('  -> Run with: sudo python3 {}'.format(sys.argv[0]))

    print()
    return ok


# ---------------------------------------------------------------------------
# BlueZ D-Bus constants
# ---------------------------------------------------------------------------

BLUEZ_SERVICE_NAME = 'org.bluez'
ADAPTER_IFACE = 'org.bluez.Adapter1'
DBUS_OM_IFACE = 'org.freedesktop.DBus.ObjectManager'
DBUS_PROP_IFACE = 'org.freedesktop.DBus.Properties'

GATT_MANAGER_IFACE = 'org.bluez.GattManager1'
GATT_SERVICE_IFACE = 'org.bluez.GattService1'
GATT_CHRC_IFACE = 'org.bluez.GattCharacteristic1'

LE_ADVERTISING_MANAGER_IFACE = 'org.bluez.LEAdvertisingManager1'
LE_ADVERTISEMENT_IFACE = 'org.bluez.LEAdvertisement1'

# Custom UUIDs for our file transfer service
FILE_TRANSFER_SERVICE_UUID = '12345678-1234-5678-1234-56789abcdef0'
FILE_CONTROL_CHRC_UUID = '12345678-1234-5678-1234-56789abcdef1'
FILE_DATA_CHRC_UUID = '12345678-1234-5678-1234-56789abcdef2'

# Control commands (first byte of writes to control characteristic)
CMD_BEGIN = 0x01
CMD_END = 0x02
CMD_ABORT = 0x03


# ---------------------------------------------------------------------------
# D-Bus helper: raise BlueZ-style errors
# ---------------------------------------------------------------------------

class InvalidArgsException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.freedesktop.DBus.Error.InvalidArgs'


class NotSupportedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.NotSupported'


class NotPermittedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.NotPermitted'


class FailedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.Failed'


# ---------------------------------------------------------------------------
# LE Advertisement
# ---------------------------------------------------------------------------

class FileTransferAdvertisement(dbus.service.Object):
    """
    BLE advertisement that advertises our file transfer service UUID.
    Implements org.bluez.LEAdvertisement1.
    """

    PATH = '/org/bluez/ldacexfil/advertisement0'

    def __init__(self, bus):
        self.bus = bus
        self._properties = {
            LE_ADVERTISEMENT_IFACE: {
                'Type': dbus.String('peripheral'),
                'ServiceUUIDs': dbus.Array([FILE_TRANSFER_SERVICE_UUID], signature='s'),
                'LocalName': dbus.String('BLE-FileServer'),
                'Includes': dbus.Array(['tx-power'], signature='s'),
            }
        }
        dbus.service.Object.__init__(self, bus, self.PATH)

    def get_path(self):
        return dbus.ObjectPath(self.PATH)

    def get_properties(self):
        return self._properties[LE_ADVERTISEMENT_IFACE]

    @dbus.service.method(DBUS_PROP_IFACE, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != LE_ADVERTISEMENT_IFACE:
            raise InvalidArgsException()
        return self.get_properties()

    @dbus.service.method(DBUS_PROP_IFACE, in_signature='ss', out_signature='v')
    def Get(self, interface, prop):
        if interface != LE_ADVERTISEMENT_IFACE:
            raise InvalidArgsException()
        props = self.get_properties()
        if prop not in props:
            raise InvalidArgsException()
        return props[prop]

    @dbus.service.method(LE_ADVERTISEMENT_IFACE, in_signature='', out_signature='')
    def Release(self):
        print('[ADV] Advertisement released by BlueZ')


# ---------------------------------------------------------------------------
# GATT Application (ObjectManager root)
# ---------------------------------------------------------------------------

class GattApplication(dbus.service.Object):
    """
    Root object for our GATT application.
    Implements org.freedesktop.DBus.ObjectManager.
    BlueZ calls GetManagedObjects() to discover services/characteristics.
    """

    PATH = '/org/bluez/ldacexfil'

    def __init__(self, bus, upload_dir):
        self.services = []
        dbus.service.Object.__init__(self, bus, self.PATH)
        self.add_service(FileTransferService(bus, 0, upload_dir))

    def get_path(self):
        return dbus.ObjectPath(self.PATH)

    def add_service(self, service):
        self.services.append(service)

    @dbus.service.method(DBUS_OM_IFACE, out_signature='a{oa{sa{sv}}}')
    def GetManagedObjects(self):
        response = {}
        for service in self.services:
            response[service.get_path()] = service.get_properties()
            for chrc in service.characteristics:
                response[chrc.get_path()] = chrc.get_properties()
        return response


# ---------------------------------------------------------------------------
# GATT Service base
# ---------------------------------------------------------------------------

class GattService(dbus.service.Object):
    """Base class for a BlueZ GattService1 D-Bus object."""

    def __init__(self, bus, index, uuid, primary):
        self.path = '{}/service{}'.format(GattApplication.PATH, index)
        self.bus = bus
        self.uuid = uuid
        self.primary = primary
        self.characteristics = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_characteristic(self, characteristic):
        self.characteristics.append(characteristic)

    def get_properties(self):
        return {
            GATT_SERVICE_IFACE: {
                'UUID': self.uuid,
                'Primary': self.primary,
            }
        }

    @dbus.service.method(DBUS_PROP_IFACE, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_SERVICE_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[GATT_SERVICE_IFACE]

    @dbus.service.method(DBUS_PROP_IFACE, in_signature='ss', out_signature='v')
    def Get(self, interface, prop):
        if interface != GATT_SERVICE_IFACE:
            raise InvalidArgsException()
        props = self.get_properties()[GATT_SERVICE_IFACE]
        if prop not in props:
            raise InvalidArgsException()
        return props[prop]


# ---------------------------------------------------------------------------
# GATT Characteristic base
# ---------------------------------------------------------------------------

class GattCharacteristic(dbus.service.Object):
    """Base class for a BlueZ GattCharacteristic1 D-Bus object."""

    def __init__(self, bus, index, uuid, flags, service):
        self.path = '{}/char{}'.format(service.get_path(), index)
        self.bus = bus
        self.uuid = uuid
        self.flags = flags
        self.service = service
        dbus.service.Object.__init__(self, bus, self.path)
        service.add_characteristic(self)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        return {
            GATT_CHRC_IFACE: {
                'Service': self.service.get_path(),
                'UUID': self.uuid,
                'Flags': self.flags,
            }
        }

    @dbus.service.method(DBUS_PROP_IFACE, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_CHRC_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[GATT_CHRC_IFACE]

    @dbus.service.method(DBUS_PROP_IFACE, in_signature='ss', out_signature='v')
    def Get(self, interface, prop):
        if interface != GATT_CHRC_IFACE:
            raise InvalidArgsException()
        props = self.get_properties()[GATT_CHRC_IFACE]
        if prop not in props:
            raise InvalidArgsException()
        return props[prop]

    @dbus.service.method(GATT_CHRC_IFACE, in_signature='a{sv}', out_signature='ay')
    def ReadValue(self, options):
        raise NotSupportedException()

    @dbus.service.method(GATT_CHRC_IFACE, in_signature='aya{sv}', out_signature='')
    def WriteValue(self, value, options):
        raise NotSupportedException()

    @dbus.service.method(GATT_CHRC_IFACE, in_signature='', out_signature='')
    def StartNotify(self):
        raise NotSupportedException()

    @dbus.service.method(GATT_CHRC_IFACE, in_signature='', out_signature='')
    def StopNotify(self):
        raise NotSupportedException()


# ---------------------------------------------------------------------------
# File Transfer Service
# ---------------------------------------------------------------------------

class FileTransferService(GattService):
    """
    Custom GATT service for receiving file uploads.
    Contains two characteristics: control and data.
    """

    def __init__(self, bus, index, upload_dir):
        super().__init__(bus, index, FILE_TRANSFER_SERVICE_UUID, True)
        self.upload_dir = upload_dir

        # Shared transfer state (one transfer at a time)
        self.transfer_state = {
            'active': False,
            'filename': None,
            'temp_file': None,
            'bytes_received': 0,
        }

        FileControlCharacteristic(bus, 0, self)
        FileDataCharacteristic(bus, 1, self)


class FileControlCharacteristic(GattCharacteristic):
    """
    Control characteristic for file transfers.

    Write protocol:
      0x01 + <UTF-8 filename bytes> = begin a new file transfer
      0x02                          = finalize transfer (save file)
      0x03                          = abort transfer (discard)
    """

    def __init__(self, bus, index, service):
        super().__init__(
            bus, index,
            FILE_CONTROL_CHRC_UUID,
            ['write', 'write-without-response'],
            service,
        )

    @dbus.service.method(GATT_CHRC_IFACE, in_signature='aya{sv}', out_signature='')
    def WriteValue(self, value, options):
        state = self.service.transfer_state
        data = bytes(value)

        if len(data) < 1:
            raise InvalidArgsException()

        cmd = data[0]

        if cmd == CMD_BEGIN:
            # Begin new transfer: remaining bytes are the filename
            if len(data) < 2:
                raise InvalidArgsException()

            raw_filename = data[1:].decode('utf-8', errors='replace')
            # Sanitize: take only the basename, strip path separators
            filename = os.path.basename(raw_filename).strip()
            if not filename:
                filename = 'unnamed_upload'

            # Abort any existing transfer
            if state['active'] and state['temp_file']:
                try:
                    state['temp_file'].close()
                    os.unlink(state['temp_file'].name)
                except OSError:
                    pass

            # Create temp file in the upload directory
            os.makedirs(self.service.upload_dir, exist_ok=True)
            temp_fd = tempfile.NamedTemporaryFile(
                dir=self.service.upload_dir,
                prefix='.upload_',
                delete=False,
            )

            state['active'] = True
            state['filename'] = filename
            state['temp_file'] = temp_fd
            state['bytes_received'] = 0

            print('[CTRL] Transfer BEGIN: filename={!r}'.format(filename))

        elif cmd == CMD_END:
            if not state['active']:
                print('[CTRL] END received but no active transfer — ignoring')
                return

            temp_fd = state['temp_file']
            temp_fd.close()

            # Move temp file to final destination
            final_path = os.path.join(self.service.upload_dir, state['filename'])
            # Avoid overwriting: append counter if needed
            if os.path.exists(final_path):
                base, ext = os.path.splitext(final_path)
                counter = 1
                while os.path.exists(final_path):
                    final_path = '{}_{}{}'.format(base, counter, ext)
                    counter += 1

            shutil.move(temp_fd.name, final_path)
            print('[CTRL] Transfer END: saved {} bytes to {}'.format(
                state['bytes_received'], final_path
            ))

            state['active'] = False
            state['filename'] = None
            state['temp_file'] = None
            state['bytes_received'] = 0

        elif cmd == CMD_ABORT:
            if state['active'] and state['temp_file']:
                try:
                    state['temp_file'].close()
                    os.unlink(state['temp_file'].name)
                except OSError:
                    pass
            print('[CTRL] Transfer ABORTED')
            state['active'] = False
            state['filename'] = None
            state['temp_file'] = None
            state['bytes_received'] = 0

        else:
            raise InvalidArgsException()


class FileDataCharacteristic(GattCharacteristic):
    """
    Data characteristic for receiving file content chunks.
    Each write appends raw bytes to the current transfer's temp file.
    """

    def __init__(self, bus, index, service):
        super().__init__(
            bus, index,
            FILE_DATA_CHRC_UUID,
            ['write', 'write-without-response'],
            service,
        )

    @dbus.service.method(GATT_CHRC_IFACE, in_signature='aya{sv}', out_signature='')
    def WriteValue(self, value, options):
        state = self.service.transfer_state

        if not state['active']:
            raise FailedException('No active transfer. Send BEGIN command first.')

        data = bytes(value)
        state['temp_file'].write(data)
        state['bytes_received'] += len(data)

        if state['bytes_received'] % (50 * 1024) < len(data):
            # Log progress roughly every 50 KB
            print('[DATA] Received {} bytes so far...'.format(state['bytes_received']))


# ---------------------------------------------------------------------------
# Adapter helpers
# ---------------------------------------------------------------------------

def find_adapter(bus, adapter_name):
    """Find the BlueZ adapter object and verify it supports GATT manager."""
    adapter_path = '/org/bluez/{}'.format(adapter_name)
    try:
        adapter_obj = bus.get_object(BLUEZ_SERVICE_NAME, adapter_path)
    except dbus.exceptions.DBusException:
        return None
    return adapter_obj


def power_on_adapter(bus, adapter_obj):
    """Ensure the adapter is powered on."""
    props = dbus.Interface(adapter_obj, DBUS_PROP_IFACE)
    powered = props.Get(ADAPTER_IFACE, 'Powered')
    if not powered:
        print('[SETUP] Powering on adapter...')
        props.Set(ADAPTER_IFACE, 'Powered', dbus.Boolean(True))
        print('[SETUP] Adapter powered on')
    else:
        print('[SETUP] Adapter already powered on')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='BLE GATT File Transfer Server')
    parser.add_argument(
        '--adapter', default='hci0',
        help='Bluetooth adapter name (default: hci0)'
    )
    parser.add_argument(
        '--upload-dir', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads'),
        help='Directory to store uploaded files (default: ./uploads)'
    )
    parser.add_argument(
        '--skip-checks', action='store_true',
        help='Skip dependency checks'
    )
    args = parser.parse_args()

    print('=== BLE GATT File Transfer Server ===')
    print()

    # Dependency checks
    if not args.skip_checks:
        print('--- Dependency Checks ---')
        if not check_dependencies(args.adapter):
            print('Some checks failed. Fix the issues above and try again.')
            print('You can skip checks with --skip-checks if you know what you are doing.')
            sys.exit(1)
        print('All checks passed.')
        print()

    # Ensure upload directory exists
    os.makedirs(args.upload_dir, exist_ok=True)
    print('[SETUP] Upload directory: {}'.format(os.path.abspath(args.upload_dir)))

    # Set up D-Bus main loop
    import dbus.mainloop.glib
    from gi.repository import GLib

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    # Find adapter
    adapter_obj = find_adapter(bus, args.adapter)
    if not adapter_obj:
        print('[ERROR] Adapter {} not found on D-Bus.'.format(args.adapter))
        sys.exit(1)

    # Power on adapter
    power_on_adapter(bus, adapter_obj)

    # Create and register the GATT application
    app = GattApplication(bus, args.upload_dir)
    gatt_manager = dbus.Interface(adapter_obj, GATT_MANAGER_IFACE)

    # Create and register the advertisement
    adv = FileTransferAdvertisement(bus)
    ad_manager = dbus.Interface(adapter_obj, LE_ADVERTISING_MANAGER_IFACE)

    mainloop = GLib.MainLoop()

    def on_app_registered():
        print('[GATT] Application registered successfully')

    def on_app_register_error(error):
        print('[GATT] Failed to register application: {}'.format(error))
        mainloop.quit()

    def on_adv_registered():
        print('[ADV]  Advertisement registered successfully')
        print()
        print('=== Server is running ===')
        print('Service UUID: {}'.format(FILE_TRANSFER_SERVICE_UUID))
        print('Waiting for connections... (Ctrl+C to stop)')
        print()

    def on_adv_register_error(error):
        print('[ADV]  Failed to register advertisement: {}'.format(error))
        mainloop.quit()

    print('[SETUP] Registering GATT application...')
    gatt_manager.RegisterApplication(
        app.get_path(), {},
        reply_handler=on_app_registered,
        error_handler=on_app_register_error,
    )

    print('[SETUP] Registering BLE advertisement...')
    ad_manager.RegisterAdvertisement(
        adv.get_path(), {},
        reply_handler=on_adv_registered,
        error_handler=on_adv_register_error,
    )

    try:
        mainloop.run()
    except KeyboardInterrupt:
        print()
        print('[SHUTDOWN] Stopping server...')

    # Cleanup
    try:
        ad_manager.UnregisterAdvertisement(adv.get_path())
    except Exception:
        pass
    try:
        gatt_manager.UnregisterApplication(app.get_path())
    except Exception:
        pass

    print('[SHUTDOWN] Done.')


if __name__ == '__main__':
    main()

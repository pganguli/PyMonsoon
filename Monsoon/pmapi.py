import ctypes
import os
import platform
import struct
import time

import numpy as np
import usb.core
import usb.util

from Monsoon import Operations as op


class USB_protocol(object):
    """Uses native python usb functions to communicate with the Power Monitor.
    Best choice for connecting to a single Power Monitor."""

    def __init__(self):
        self.DEVICE = None
        self.epBulkWriter = None
        self.epBulkReader = None

    def enumerateDevices(self):
        """Returns a list of the serial numbers of all devices connected to the system.
        Includes both HVPM and LVPM hardware."""
        results = []
        devices = usb.core.find(find_all=True, idVendor=0x2AB9, idProduct=0x0001)
        if devices:
            for device in devices:
                try:
                    if device.serial_number:
                        results.append(str(device.serial_number))
                except Exception:
                    pass
        return results

    def reconnect(self, deviceType, serialno):
        """Reset the port and reconnect to the power monitor."""
        if self.DEVICE:
            try:
                self.DEVICE.reset()
            except Exception:
                pass
        time.sleep(5)
        self.Connect(deviceType, serialno)

    def Connect(self, deviceType, serialno=None):
        """Connect to a Power Monitor.
        deviceType = LVPM or HVPM
        serialno = device serial number. If None, connect to the first device found."""

        def device_matcher(d):
            try:
                return (
                    d.idVendor == 0x2AB9
                    and d.idProduct == 0x0001
                    and (serialno is None or str(d.serial_number) == str(serialno))
                )
            except Exception:
                return False

        self.DEVICE = usb.core.find(custom_match=device_matcher)
        if self.DEVICE is None:
            print("Unable to find device")
            return

        connectedDeviceType = self.getValue(op.OpCodes.HardwareModel, 2)
        if connectedDeviceType != deviceType:
            print(
                f"Warning: Device type mismatch. Found {connectedDeviceType!r} expected {deviceType!r}"
            )

        firmwareRev = self.getValue(op.OpCodes.FirmwareVersion, 1)
        if firmwareRev < op.ReturnCodes.CURRENT_FIRMWARE_REV:
            print(
                f"Warning: Detected firmware revision {firmwareRev!r}, current release is {op.ReturnCodes.CURRENT_FIRMWARE_REV!r}"
            )

        # On Linux detach usb HID driver first if attached
        if platform.system() == "Linux":
            try:
                if self.DEVICE.is_kernel_driver_active(0):
                    self.DEVICE.detach_kernel_driver(0)
            except Exception:
                pass

        self.DEVICE.set_configuration()
        cfg = self.DEVICE.get_active_configuration()
        intf = cfg[(0, 0)]

        self.epBulkWriter = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: (
                usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
            ),
        )
        self.epBulkReader = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: (
                usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN
            ),
        )

    def BulkRead(self):
        if self.DEVICE:
            return self.DEVICE.read(0x81, 64, timeout=1000)
        return []

    def sendCommand(self, operation, value):
        """Send a USB Control transfer. Normally this is used to set an EEPROM value."""
        if not self.verifyReady(operation):
            self.stopSampling()
            raise ValueError(
                "Power Monitor Error, attempted to send a command while the unit is in Sample Mode."
            )

        value = int(value)
        value_array = struct.unpack("4B", struct.pack("I", value))
        operation_array = struct.unpack("4b", struct.pack("I", operation))
        wValue = struct.unpack("H", struct.pack("BB", value_array[0], value_array[1]))[
            0
        ]
        wIndex = struct.unpack(
            "H", struct.pack("BB", operation_array[0], value_array[2])
        )[0]
        self.DEVICE.ctrl_transfer(
            op.Control_Codes.USB_OUT_PACKET,
            op.Control_Codes.USB_SET_VALUE,
            wValue,
            wIndex,
            value_array,
            5000,
        )

    def stopSampling(self):
        """Send a control transfer instructing the Power Monitor to stop sampling."""
        if self.DEVICE:
            self.verifyReady(0x02)
            self.DEVICE.ctrl_transfer(
                op.Control_Codes.USB_OUT_PACKET,
                op.Control_Codes.USB_REQUEST_STOP,
                0,
                0,
                0,
                5000,
            )

    def startSampling(self, calTime, maxTime):
        """Instruct the Power Monitor to enter sample mode."""
        if not self.verifyReady(0x02):
            self.stopSampling()
            raise ValueError(
                "Power Monitor Error, attempted to start while already started."
            )

        value_array = struct.unpack("4B", struct.pack("I", calTime))
        maxtime_array = struct.unpack("4B", struct.pack("I", maxTime))
        wValue = struct.unpack("H", struct.pack("BB", value_array[0], value_array[1]))[
            0
        ]
        wIndex = struct.unpack("H", struct.pack("BB", 0, 0))[0]
        self.DEVICE.ctrl_transfer(
            op.Control_Codes.USB_OUT_PACKET,
            op.Control_Codes.USB_REQUEST_START,
            wValue,
            wIndex,
            maxtime_array,
            1000,
        )

    def resetToBootloader(self):
        try:
            self.DEVICE.ctrl_transfer(
                op.Control_Codes.USB_OUT_PACKET,
                op.Control_Codes.USB_REQUEST_RESET_TO_BOOTLOADER,
                0,
                0,
                0,
                1000,
            )
        except Exception:
            print("Resetting to bootloader")

    def getValue(self, operation, valueLength, signed=False):
        """Get an EEPROM value from the Power Monitor."""
        operation_array = struct.unpack("4b", struct.pack("I", operation))
        wIndex = struct.unpack("H", struct.pack("bb", operation_array[0], 0))[0]
        result = self.DEVICE.ctrl_transfer(
            op.Control_Codes.USB_IN_PACKET,
            op.Control_Codes.USB_SET_VALUE,
            0,
            wIndex,
            4,
            5000,
        )

        result_bytes = bytes(result)

        # Check if the returned 4-byte payload indicates hardware error code
        if len(result_bytes) == 4:
            unpacked_raw = struct.unpack("<I", result_bytes)[0]
            if unpacked_raw == op.ReturnCodes.ERROR:
                self.stopSampling()
                raise ValueError(
                    "Error code returned. Attempted to query Power Monitor while in sample mode."
                )

        if valueLength == 4:
            fmt = "i" if signed else "I"
            return struct.unpack(fmt, result_bytes[:4])[0]
        elif valueLength == 2:
            fmt = "h" if signed else "H"
            return struct.unpack(fmt, result_bytes[:2])[0]
        elif valueLength == 1:
            fmt = "b" if signed else "B"
            return struct.unpack(fmt, result_bytes[:1])[0]
        return result

    def closeDevice(self):
        """Cleanup any loose ends safely."""
        if self.DEVICE:
            try:
                self.stopSampling()
            except Exception:
                pass
            try:
                self.DEVICE.reset()
            except Exception:
                pass
            try:
                usb.util.dispose_resources(self.DEVICE)
            except Exception:
                pass
            self.DEVICE = None

    def verifyReady(self, opcode):
        firmwareRev = self.getValue(op.OpCodes.FirmwareVersion, 1)
        if firmwareRev >= 26:
            status = self.getValue(op.OpCodes.getStartStatus, 1)
            return not bool(np.bitwise_and(0x80, status))
        return True


class CPP_Backend_Protocol(object):
    """Uses C++ backend with libusb for low-latency multi-device collection."""

    def __init__(self):
        self.DEVICE = self.loadLibrary()
        self.DEVICE.pySetup.argtypes = (ctypes.c_int, ctypes.c_int, ctypes.c_int)
        self.DEVICE.pyStart.argtypes = (ctypes.c_int, ctypes.c_int)
        self.DEVICE.pyGetBulkData.argtypes = (
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_uint8),
        )
        self.DEVICE.pySendCommand.argtypes = (ctypes.c_ubyte, ctypes.c_int)
        self.DEVICE.pyGetValue.argtypes = (ctypes.c_ubyte, ctypes.c_int)

        self.queueSize = 1024
        self.Queue = (ctypes.c_uint8 * self.queueSize)()
        ctypes.cast(self.Queue, ctypes.POINTER(ctypes.c_uint8))

    def Connect(self, deviceType, serialno=None):
        VID = 0x2AB9
        PID = 0x0001
        ser_val = 0 if serialno is None else int(serialno)
        self.DEVICE.pySetup(VID, PID, ser_val)

    def BulkRead(self):
        self.DEVICE.pyGetBulkData(self.queueSize, self.Queue)
        count = self.DEVICE.pyQueueCount()
        return list(self.Queue[0 : count * 64])

    def sendCommand(self, operation, value):
        self.DEVICE.pySendCommand(operation, int(value))

    def stopSampling(self):
        self.DEVICE.pyStop()

    def startSampling(self, calTime, maxTime):
        self.DEVICE.pyStart(calTime, maxTime)

    def getValue(self, operation, valueLength):
        return self.DEVICE.pyGetValue(operation, valueLength)

    def closeDevice(self):
        if hasattr(self.DEVICE, "pyClose"):
            try:
                self.DEVICE.pyClose()
            except Exception:
                pass

    def loadLibrary(self):
        path = os.path.dirname(os.path.realpath(__file__))
        sys_name = platform.system()

        if sys_name == "Linux":
            libLocation = os.path.join(path, "Compiled/Linux/libcpp_backend.so")
        elif sys_name == "Windows":
            libLocation = os.path.join(path, "Compiled/WIN32/Cpp_backend.dll")
        else:
            raise NotImplementedError(f"OS '{sys_name}' not currently supported.")

        return ctypes.CDLL(libLocation)

    def reconnect(self):
        raise NotImplementedError

    def findAllSerialNumbers(self):
        raise NotImplementedError

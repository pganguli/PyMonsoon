import platform
import usb.core
import usb.util
import struct
from Monsoon import Operations as op

DEVICE = None
DEVICE_TYPE = None
epBulkWriter = None
epBulkReader = None
VID = "0x2ab9"
PID = "0xffff"


class bootloaderMonsoon(object):
    def __init__(self, *args, **kwargs):
        pass

    def setup_usb(self):
        """Sets up the USB connection."""
        global DEVICE
        global epBulkWriter
        global epBulkReader
        global VID
        global PID

        DEVICE = usb.core.find(idVendor=0x2AB9, idProduct=0xFFFF)
        if DEVICE is None:  # If not a LVPM, look for an HVPM.
            DEVICE = usb.core.find(idVendor=0x04D8, idProduct=0x000B)
            VID = "0x4d8"
            PID = "0xb"
        if "Linux" == platform.system():
            try:
                DEVICE.detach_kernel_driver(0)
            except Exception:
                pass  # already unregistered
        DEVICE.set_configuration()

        cfg = DEVICE.get_active_configuration()
        intf = cfg[(0, 0)]

        epBulkWriter = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: (
                usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
            ),
        )
        epBulkReader = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: (
                usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN
            ),
        )

    def __bootCommand(self, Command, length, address, data):
        """Sends boot command."""
        sendData = []
        sendData.append(Command)
        sendData.append(length)
        sendData.append(address[2])
        sendData.append(address[1])
        sendData.append(address[0])
        for i in range(0, len(data)):
            sendData.append(data[i])
        for i in range(len(data), length):
            sendData.append(0)
        epBulkWriter.write(sendData, timeout=10000)
        ret = epBulkReader.read(length + 5, timeout=10000)
        return ret

    def writeFlash(self, hex_):
        """Writes a hex file to the Power Monitor's PIC. Uses Intel HEX file format."""
        Flash, EEPROM, IDlocs, Config = self.__formatHex(hex_)
        print("Erasing Flash...")
        self.__writeRegion(
            op.BootloaderMemoryRegions.Flash,
            op.BootloaderCommands.EraseFlash,
            0x0800,
            Flash,
            None,
        )
        print("Writing Flash...")
        if self.__writeRegion(
            op.BootloaderMemoryRegions.Flash,
            op.BootloaderCommands.WriteFlash,
            0x0800,
            Flash,
            op.BootloaderCommands.ReadFlash,
        ):
            print("Flash written OK")
        if self.__writeChunk(
            op.BootloaderMemoryRegions.IDLocs,
            op.BootloaderCommands.WriteFlash,
            0x0000,
            IDlocs,
            op.BootloaderCommands.ReadFlash,
        ):
            print("IDLocs written OK")
        if self.__writeChunk(
            op.BootloaderMemoryRegions.Config,
            op.BootloaderCommands.WriteConfig,
            0x0000,
            Config,
            op.BootloaderCommands.ReadConfig,
        ):
            print("Config written OK")

    def __writeRegion(
        self, memoryRegion, command, addressStart, regionData, errorCheckCommand
    ):
        """Writes information to a memory region."""
        address = [0 for _ in range(3)]
        result = True
        progressThresholds = [x * 10 for x in range(11)]
        progressindex = 0
        for i in range(addressStart, len(regionData), 16):
            memoryIndex = struct.unpack("BBBB", struct.pack("I", i))
            address[0] = memoryRegion
            address[1] = memoryIndex[1]
            address[2] = memoryIndex[0]
            data = regionData[i : i + 16]
            self.__bootCommand(command, len(data), address, data)
            if errorCheckCommand is not None:
                dataout = self.__bootCommand(errorCheckCommand, 16, address, [])
                dataout = dataout[5:]
                if not self.__compare(data, dataout):
                    result = False
                    print("Write error")
            percentComplete = (i / len(regionData)) * 100
            if (
                progressindex < len(progressThresholds)
                and progressThresholds[progressindex] < percentComplete
            ):
                print("%.0f percent complete" % percentComplete)
                progressindex += 1
        return result

    def __writeChunk(
        self, memoryRegion, command, addressStart, regionData, errorCheckCommand
    ):
        result = True
        address = [memoryRegion, 0, 0]
        data = regionData
        if memoryRegion != op.BootloaderMemoryRegions.Config:
            self.__bootCommand(op.BootloaderCommands.EraseFlash, 16, address, [])
        self.__bootCommand(command, len(data), address, data)
        return result

    def __compare(self, data, dataout):
        """Compare read data to the data we think we wrote."""
        if data is None or dataout is None:
            return False
        if len(data) != len(dataout):
            return False
        for i in range(len(data)):
            if data[i] != dataout[i]:
                return False
        return True

    def __byteLine(self, line):
        """Translate a HEX file line into address, linetype, data, and checksum"""
        output = []
        for offset in range(1, len(line) - 1, 2):
            output.append(int(line[offset : offset + 2], 16))
        length = output[0]
        address = [output[1], output[2]]
        type_ = output[3]
        Data = output[4 : 4 + length]
        checksum = output[-1]
        return address, type_, Data, checksum

    def getHeaderFromFWM(self, filename):
        """Strips the header from a Monsoon FWM file, returns the HEX file and the formatted header.
        Header format [VID,PID,Rev,Model]"""
        with open(filename, "r", encoding="latin1") as f:
            hex_ = f.read()

        headerEnd = hex_.find(":")
        header = hex_[0:headerEnd]
        offset = 7
        count = ord(header[offset])
        offset += 1
        hex_ = hex_[headerEnd:]

        headers = []
        for _ in range(count):
            vid = ord(header[offset]) | (ord(header[offset + 1]) << 8)
            offset += 2
            pid = ord(header[offset]) | (ord(header[offset + 1]) << 8)
            offset += 2
            rev = ord(header[offset]) | (ord(header[offset + 1]) << 8)
            offset += 2
            model = ord(header[offset]) | (ord(header[offset + 1]) << 8)
            offset += 2
            headers.append([vid, pid, rev, model])

        return headers, hex_

    def getHexFile(self, filename):
        """Reads an Intel HEX file."""
        with open(filename, "r") as f:
            hex_ = f.read()
        return hex_

    def __formatHex(self, hex_):
        """Takes raw hex_ input, and turns it into an array of hex_ lines."""
        output = []
        lineEnd = hex_.find("\n")
        while lineEnd > 0:
            output.append(hex_[0:lineEnd])
            hex_ = hex_[lineEnd + 1 :]
            lineEnd = hex_.find("\n")
        Flash, EEPROM, IDlocs, Config = self.__formatAsPICFlash(output)
        return Flash, EEPROM, IDlocs, Config

    def __formatAsPICFlash(self, hex_):
        """Formats an array of hex_ lines as PIC memory regions."""
        flash = [0xFF for _ in range(32768)]
        EEPROM = [0xFF for _ in range(256)]
        IDlocs = [0xFF for _ in range(16)]
        Config = [0xFF for _ in range(14)]
        addressMSB = 0
        for line in hex_:
            if not line.strip():
                continue
            address, type_, Data, _ = self.__byteLine(line)
            intAddress = (address[0] << 8) | address[1]
            if type_ == op.hexLineType.ExtendedLinearAddress:
                addressMSB = Data[1]
            if type_ == op.hexLineType.Data:
                if addressMSB == op.BootloaderMemoryRegions.Flash:
                    for byte in Data:
                        flash[intAddress] = byte
                        intAddress += 1
                elif addressMSB == op.BootloaderMemoryRegions.EEPROM:
                    intAddress = address[1]
                    for byte in Data:
                        EEPROM[intAddress] = byte
                        intAddress += 1
                elif addressMSB == op.BootloaderMemoryRegions.IDLocs:
                    intAddress = address[1]
                    for byte in Data:
                        IDlocs[intAddress] = byte
                        intAddress += 1
                elif addressMSB == op.BootloaderMemoryRegions.Config:
                    intAddress = address[1]
                    for byte in Data:
                        Config[intAddress] = byte
                        intAddress += 1
        return flash, EEPROM, IDlocs, Config

    def verifyHeader(self, headers):
        """Verifies the header matches the physical hardware being reflashed."""
        target_vid = int(VID, 16)
        target_pid = int(PID, 16)
        for head in headers:
            if head[0] == target_vid and head[1] == target_pid:
                return True
        return False

    def getSerialNumber(self):
        """Reads the EEPROM serial number directly."""
        address = [op.BootloaderMemoryRegions.EEPROM, 0, 8]
        ret = self.__bootCommand(op.BootloaderCommands.ReadEEPROM, 2, address, [])
        rawSerial = ret[5:7]
        serialno = rawSerial[0] | (rawSerial[1] << 8)
        return serialno

    def resetToMainSection(self):
        """Exits bootloader mode and returns to normal mode."""
        try:
            self.__bootCommand(op.BootloaderCommands.Reset, 1, [0, 0, 0], [])
        except Exception:
            print("Resetting to Main Section.")

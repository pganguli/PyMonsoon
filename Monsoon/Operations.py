class OpCodes:
    """USB Control Transfer operation codes"""

    setMainFineResistorOffset = (
        0x02  # LVPM Calibration value, 8-bits signed, ohms = 0.05 + 0.0001*offset
    )
    setMainCoarseResistorOffset = (
        0x11  # LVPM Calibration value, 8-bits signed, ohms = 0.05 + 0.0001*offset
    )
    setUsbFineResistorOffset = (
        0x0D  # LVPM Calibration value, 8-bits signed, ohms = 0.05 + 0.0001*offset
    )
    setUsbCoarseResistorOffset = (
        0x12  # LVPM Calibration value, 8-bits signed, ohms = 0.05 + 0.0001*offset
    )
    setAuxFineResistorOffset = (
        0x0E  # LVPM Calibration value, 8-bits signed, ohms = 0.1 + 0.0001*offset
    )
    setAuxCoarseResistorOffset = (
        0x13  # LVPM Calibration value, 8-bits signed, ohms = 0.1 + 0.0001*offset
    )
    calibrateMainVoltage = (
        0x03  # Internal voltage calibration, affects accuracy of setHVMainVoltage
    )
    resetPowerMonitor = 0x05  # Reset the PIC. Causes disconnect.
    setPowerupTime = (
        0x0C  # Time in milliseconds that the powerup current limit is in effect.
    )
    setTemperatureLimit = 0x29  # Temperature limit in Signed Q7.8 format
    setUsbPassthroughMode = 0x10  # Sets USB Passthrough mode: Off = 0, On = 1, Auto = 2
    setMainFineScale = 0x1A  # HVPM Calibration value, 32-bits, unsigned
    setMainCoarseScale = 0x1B  # HVPM Calibration value, 32-bits, unsigned
    setUSBFineScale = 0x1C  # HVPM Calibration value, 32-bits, unsigned
    setUSBCoarseScale = 0x1D  # HVPM Calibration value, 32-bits, unsigned
    setAuxFineScale = 0x1E  # HVPM Calibration value, 32-bits, unsigned
    setAuxCoarseScale = 0x1F  # HVPM Calibration value, 32-bits, unsigned
    setVoltageChannel = 0x23  # Sets voltage channel: 00 = Main & USB, 01 = Main & Aux
    SetPowerUpCurrentLimit = 0x43  # Sets power-up current limit (HV Amps = 15.625*(1-limit/65535), LV Amps = 8.0*(1-limit/1023))
    SetRunCurrentLimit = 0x44  # Sets runtime current limit
    setMainVoltage = 0x41  # Voltage = value * 1048576
    getSerialNumber = 0x42
    SetMainFineZeroOffset = 0x25  # Zero-level offset
    SetMainCoarseZeroOffset = 0x26  # Zero-level offset
    SetUSBFineZeroOffset = 0x27  # Zero-level offset
    SetUSBCoarseZeroOffset = 0x28  # Zero-level offset
    FirmwareVersion = 0xC0  # Read-only, gets the firmware version
    ProtocolVersion = 0xC1  # Read-only, gets the Protocol version
    HardwareModel = 0x45  # 0 = unknown, 1 = LV, 2 = HV
    getStartStatus = 0xC4
    dacCalLow = 0x88  # 2.5V ADC Reference Calibration
    dacCalHigh = 0x89  # 4.096V ADC Reference Calibration
    Stop = 0xFF


class ReturnCodes:
    """Status return codes"""

    ERROR = 0xFFFFFFFFE
    CURRENT_FIRMWARE_REV = 32


class HardwareModel:
    """Hardware Model Types"""

    UNKNOWN = 0
    LVPM = 1
    HVPM = 2


class Control_Codes:
    """USB Protocol codes."""

    USB_IN_PACKET = 0xC0
    USB_OUT_PACKET = 0x40
    USB_REQUEST_START = 0x02
    USB_REQUEST_STOP = 0x03
    USB_SET_VALUE = 0x01
    USB_REQUEST_RESET_TO_BOOTLOADER = 0xFF


class Conversion:
    """Values used for converting from desktop to the PIC"""

    FLOAT_TO_INT = 1048576


class USB_Passthrough:
    """Values for setting or retrieving the USB Passthrough mode."""

    Off = 0
    On = 1
    Auto = 2


class VoltageChannel:
    """Values for setting or retrieving the Voltage Channel."""

    Main = 0
    USB = 1
    Aux = 2


class statusPacket(object):
    """Values stored in the Power Monitor EEPROM. Each corresponds to an opcode."""

    def __init__(self):
        self.firmwareVersion = 0
        self.protocolVersion = 0
        self.temperature = 0
        self.serialNumber = 0
        self.powerupCurrentLimit = 0
        self.runtimeCurrentLimit = 0
        self.powerupTime = 0
        self.temperatureLimit = 0
        self.usbPassthroughMode = 0

        self.mainFineScale = 0
        self.mainCoarseScale = 0
        self.usbFineScale = 0
        self.usbCoarseScale = 0
        self.auxFineScale = 0
        self.auxCoarseScale = 0

        self.mainFineZeroOffset = 0
        self.mainCoarseZeroOffset = 0
        self.usbFineZeroOffset = 0
        self.usbCoarseZeroOffset = 0
        self.hardwareModel = 0

        self.mainFineResistorOffset = 0
        self.mainCoarseResistorOffset = 0
        self.usbFineResistorOffset = 0
        self.usbCoarseResistorOffset = 0
        self.auxFineResistorOffset = 0
        self.auxCoarseResistorOffset = 0

        self.dacCalLow = 0
        self.dacCalHigh = 0


class BootloaderCommands:
    """Bootloader opcodes. Used when reflashing the Power Monitor"""

    ReadVersion = 0x00
    ReadFlash = 0x01
    WriteFlash = 0x02
    EraseFlash = 0x03
    ReadEEPROM = 0x04
    WriteEEPROM = 0x05
    ReadConfig = 0x06
    WriteConfig = 0x07
    Reset = 0xFF


class BootloaderMemoryRegions:
    """Memory regions of the PIC18F4550"""

    Flash = 0x00
    IDLocs = 0x20
    Config = 0x30
    EEPROM = 0xF0


class hexLineType:
    """Line types used in the Intel Hex format."""

    Data = 0
    EndOfFile = 1
    ExtendedSegmentAddress = 2
    StartSegmentAddress = 3
    ExtendedLinearAddress = 4
    StartLinearAddress = 5


class SampleType(object):
    """Corresponds to the sampletype field from a sample packet."""

    Measurement = 0x00
    ZeroCal = 0x10
    invalid = 0x20
    refCal = 0x30

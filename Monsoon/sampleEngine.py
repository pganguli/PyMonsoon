#!/usr/bin/env python3

import operator
import os
import time
from enum import IntEnum

import numpy as np
import usb.core

from Monsoon import Operations as ops
from Monsoon.calibrationData import calibrationData


class Channels(IntEnum):
    timeStamp = 0
    MainCurrent = 1
    USBCurrent = 2
    AuxCurrent = 3
    MainVoltage = 4
    USBVoltage = 5


class Triggers:
    SAMPLECOUNT_INFINITE = 0xFFFFFFFF
    GREATER_THAN = staticmethod(operator.gt)
    LESS_THAN = staticmethod(operator.lt)


class ErrorHandlingModes(IntEnum):
    off = 0  # No error checking
    full = 1  # Automatically handle errors
    debug = 2  # Handle errors + output logging data


# Backward compatibility aliases for legacy scripts
channels = Channels
triggers = Triggers


class SampleEngine:
    def __init__(
        self,
        Monsoon,
        bulkProcessRate=128,
        errorMode=ErrorHandlingModes.full,
        calsToKeep=5,
    ):
        """Declares global variables and initializes calibration and channels."""
        self.monsoon = Monsoon
        self.__errorMode = errorMode

        if errorMode == ErrorHandlingModes.debug:
            os.environ["PYUSB_DEBUG"] = "debug"
            os.environ["PYUSB_LOG_FILENAME"] = "pyusb.log"
            usb._setup_log()

        self.__mainCal = calibrationData(calsToKeep)
        self.__usbCal = calibrationData(calsToKeep)
        self.__auxCal = calibrationData(calsToKeep)
        self.__padding = np.zeros((64,))
        self.__fineThreshold = Monsoon.fineThreshold
        self.__auxFineThreshold = Monsoon.auxFineThreshold
        self.__ADCRatio = (
            62.5 / 1e6
        )  # Each tick of the ADC represents this much voltage
        self.__mainVoltageScale = Monsoon.mainvoltageScale
        self.__usbVoltageScale = Monsoon.usbVoltageScale
        self.dropped = 0
        self.bulkProcessRate = bulkProcessRate
        self.__packetSize = 64
        self.__startTime = time.time()

        # Indices
        self.__mainCoarseIndex = 0
        self.__mainFineIndex = 1
        self.__usbCoarseIndex = 2
        self.__usbFineIndex = 3
        self.__auxCoarseIndex = 4
        self.__auxFineIndex = 5
        self.__mainVoltageIndex = 6
        self.__usbVoltageIndex = 7
        self.__timestampIndex = 10

        # Output lists
        self.__mainCurrent = []
        self.__usbCurrent = []
        self.__auxCurrent = []
        self.__usbVoltage = []
        self.__mainVoltage = []
        self.__timeStamps = []

        # Output controls
        self.__outputConsoleMeasurements = True
        self.__outputTimeStamp = True
        self.__collectMainMeasurements = True
        self.__collectUSBMeasurements = False
        self.__collectAuxMeasurements = False
        self.__collectMainVoltage = True
        self.__collectUSBVoltage = False

        self.__channels = [
            self.__outputTimeStamp,
            self.__collectMainMeasurements,
            self.__collectUSBMeasurements,
            self.__collectAuxMeasurements,
            self.__collectMainVoltage,
            self.__collectUSBVoltage,
        ]
        self.__channelnames = [
            "Time(ms)",
            "Main(mA)",
            "USB(mA)",
            "Aux(mA)",
            "Main Voltage(V)",
            "USB Voltage(V)",
        ]
        self.__sampleCount = 0
        self.__outputCheckNum = 0
        self.__CSVOutEnable = False
        self.__granularity = 1

        # Trigger Settings
        self.__startTriggerSet = False
        self.__stopTriggerSet = False
        self.__triggerChannel = Channels.timeStamp
        self.__startTriggerLevel = 0
        self.__startTriggerStyle = Triggers.GREATER_THAN
        self.__stopTriggerLevel = Triggers.SAMPLECOUNT_INFINITE
        self.__stopTriggerStyle = Triggers.GREATER_THAN
        self.__sampleLimit = 50000

        # Output writer
        self.__f = None
        self.__outputFilename = None

    def setStartTrigger(self, triggerStyle, triggerLevel):
        """Controls the conditions when the sampleEngine starts recording measurements."""
        self.__startTriggerLevel = triggerLevel
        self.__startTriggerStyle = triggerStyle

    def setStopTrigger(self, triggerstyle, triggerlevel):
        """Controls the conditions when the sampleEngine stops recording measurements."""
        self.__stopTriggerLevel = triggerlevel
        self.__stopTriggerStyle = triggerstyle

    def setTriggerChannel(self, triggerChannel):
        """Sets channel that controls the trigger."""
        self.__triggerChannel = triggerChannel

    def ConsoleOutput(self, boolValue):
        """Enables or disables the display of realtime measurements."""
        self.__outputConsoleMeasurements = boolValue

    def enableChannel(self, channel):
        """Enables a channel."""
        self.__channels[channel] = True

    def disableChannel(self, channel):
        """Disables a channel."""
        self.__channels[channel] = False

    def enableCSVOutput(self, filename):
        """Opens a file for outputting measurements periodically."""
        self.__outputFilename = filename
        self.__f = open(filename, "w")
        self.__CSVOutEnable = True

    def disableCSVOutput(self):
        """Closes the CSV file if open and disables CSV output."""
        if self.__f is not None:
            self.__f.close()
            self.__f = None
        self.__CSVOutEnable = False

    def __Reset(self):
        self.__startTriggerSet = False
        self.__stopTriggerSet = False
        self.__sampleCount = 0
        self.__mainCal.clear()
        self.__usbCal.clear()
        self.__auxCal.clear()
        self.__ClearOutput()

    def __ClearOutput(self):
        """Wipes away all of the old output data."""
        self.__mainCurrent = []
        self.__usbCurrent = []
        self.__auxCurrent = []
        self.__usbVoltage = []
        self.__mainVoltage = []
        self.__timeStamps = []

    def __isCalibrated(self):
        """Returns true if every channel has sufficient calibration samples."""
        return (
            self.__mainCal.calibrated()
            and self.__usbCal.calibrated()
            and self.__auxCal.calibrated()
        )

    def __addMeasurement(self, channel, measurement):
        """Adds measurements to the global list of measurements."""
        if channel == self.__triggerChannel and not self.__startTriggerSet:
            self.__evalStartTrigger(measurement)
        elif channel == self.__triggerChannel:
            self.__evalStopTrigger(measurement[:: self.__granularity])

        measurements = self.__getMeasurement(measurement)

        if channel == Channels.MainCurrent and not self.__stopTriggerSet:
            self.__mainCurrent.append(measurements)
        elif channel == Channels.USBCurrent:
            self.__usbCurrent.append(measurements)
        elif channel == Channels.AuxCurrent:
            self.__auxCurrent.append(measurements)
        elif channel == Channels.USBVoltage:
            self.__usbVoltage.append(measurements)
        elif channel == Channels.MainVoltage:
            self.__mainVoltage.append(measurements)
        elif channel == Channels.timeStamp:
            self.__timeStamps.append(measurements)
            self.__sampleCount += len(measurements)

    def __getMeasurement(self, measurement):
        sliced = measurement[:: self.__granularity]
        if (self.__sampleCount + len(sliced)) > self.__sampleLimit:
            measurements = []
            counter = self.__sampleCount
            for sample in sliced:
                if counter >= self.__sampleLimit:
                    break
                measurements.append(sample)
                counter += 1
            return measurements
        return measurement

    def __evalStartTrigger(self, measurement):
        """See if any measurements meet conditions to start recording."""
        test = self.__startTriggerStyle(np.array(measurement), self.__startTriggerLevel)
        self.__startTriggerSet = bool(np.any(test))

    def __evalStopTrigger(self, measurement):
        """See if any measurements meet conditions to stop recording."""
        if (
            self.__sampleCount >= self.__sampleLimit
            and self.__sampleLimit != Triggers.SAMPLECOUNT_INFINITE
        ):
            self.__stopTriggerSet = True
        if self.__stopTriggerLevel != Triggers.SAMPLECOUNT_INFINITE:
            test = self.__stopTriggerStyle(
                np.array(measurement), self.__stopTriggerLevel
            )
            if np.any(test):
                self.__stopTriggerSet = True

    def __vectorProcess(self, measurements):
        """Translates raw ADC measurements into current values."""
        if not self.__isCalibrated():
            return

        measurements = np.array(measurements)
        debug_parts = []

        if self.__channels[Channels.MainCurrent]:
            # Main Coarse
            scale = self.monsoon.statusPacket.mainCoarseScale
            zeroOffset = (
                self.monsoon.statusPacket.mainCoarseZeroOffset
                + self.__mainCal.getZeroCal(True)
            )
            calRef = self.__mainCal.getRefCal(True)
            slope = scale / (calRef - zeroOffset) if (calRef - zeroOffset) != 0 else 0
            raw = measurements[:, self.__mainCoarseIndex] - zeroOffset
            mainCoarseCurrents = raw * slope

            # Main Fine
            scale = self.monsoon.statusPacket.mainFineScale
            zeroOffset = (
                self.monsoon.statusPacket.mainFineZeroOffset
                + self.__mainCal.getZeroCal(False)
            )
            calRef = self.__mainCal.getRefCal(False)
            slope = scale / (calRef - zeroOffset) if (calRef - zeroOffset) != 0 else 0
            raw = measurements[:, self.__mainFineIndex] - zeroOffset
            mainFineCurrents = raw * slope / 1000

            mainCurrent = np.where(
                measurements[:, self.__mainFineIndex] < self.__fineThreshold,
                mainFineCurrents,
                mainCoarseCurrents,
            )
            self.__addMeasurement(Channels.MainCurrent, mainCurrent)
            debug_parts.append(f"Main Current: {round(mainCurrent[0], 2)}")

        if self.__channels[Channels.USBCurrent]:
            # USB Coarse
            scale = self.monsoon.statusPacket.usbCoarseScale
            zeroOffset = (
                self.monsoon.statusPacket.usbCoarseZeroOffset
                + self.__usbCal.getZeroCal(True)
            )
            calRef = self.__usbCal.getRefCal(True)
            slope = scale / (calRef - zeroOffset) if (calRef - zeroOffset) != 0 else 0
            raw = measurements[:, self.__usbCoarseIndex] - zeroOffset
            usbCoarseCurrents = raw * slope

            # USB Fine
            scale = self.monsoon.statusPacket.usbFineScale
            zeroOffset = (
                self.monsoon.statusPacket.usbFineZeroOffset
                + self.__usbCal.getZeroCal(False)
            )
            calRef = self.__usbCal.getRefCal(False)
            slope = scale / (calRef - zeroOffset) if (calRef - zeroOffset) != 0 else 0
            raw = measurements[:, self.__usbFineIndex] - zeroOffset
            usbFineCurrents = raw * slope / 1000

            usbCurrent = np.where(
                measurements[:, self.__usbFineIndex] < self.__fineThreshold,
                usbFineCurrents,
                usbCoarseCurrents,
            )
            self.__addMeasurement(Channels.USBCurrent, usbCurrent)
            debug_parts.append(f"USB Current: {round(usbCurrent[0], 2)}")

        if self.__channels[Channels.AuxCurrent]:
            # Aux Coarse
            scale = self.monsoon.statusPacket.auxCoarseScale
            zeroOffset = self.__auxCal.getZeroCal(True)
            calRef = self.__auxCal.getRefCal(True)
            slope = scale / (calRef - zeroOffset) if (calRef - zeroOffset) != 0 else 0
            raw = measurements[:, self.__auxCoarseIndex] - zeroOffset
            auxCoarseCurrents = raw * slope

            # Aux Fine
            scale = self.monsoon.statusPacket.auxFineScale
            zeroOffset = self.__auxCal.getZeroCal(False)
            calRef = self.__auxCal.getRefCal(False)
            slope = scale / (calRef - zeroOffset) if (calRef - zeroOffset) != 0 else 0
            raw = measurements[:, self.__auxFineIndex] - zeroOffset
            auxFineCurrents = raw * slope / 1000

            auxCurrent = np.where(
                measurements[:, self.__auxFineIndex] < self.__auxFineThreshold,
                auxFineCurrents,
                auxCoarseCurrents,
            )
            self.__addMeasurement(Channels.AuxCurrent, auxCurrent)
            debug_parts.append(f"Aux Current: {round(auxCurrent[0], 2)}")

        # Voltages
        if self.__channels[Channels.MainVoltage]:
            mainVoltages = (
                measurements[:, self.__mainVoltageIndex]
                * self.__ADCRatio
                * self.__mainVoltageScale
            )
            self.__addMeasurement(Channels.MainVoltage, mainVoltages)
            debug_parts.append(f"Main Voltage: {round(mainVoltages[0], 2)}")

        if self.__channels[Channels.USBVoltage]:
            usbVoltages = (
                measurements[:, self.__usbVoltageIndex]
                * self.__ADCRatio
                * self.__usbVoltageScale
            )
            self.__addMeasurement(Channels.USBVoltage, usbVoltages)
            debug_parts.append(f"USB Voltage: {round(usbVoltages[0], 2)}")

        timeStamp = measurements[:, self.__timestampIndex]
        self.__addMeasurement(Channels.timeStamp, timeStamp)

        debug_parts.append(f"Dropped: {self.dropped}")
        debug_parts.append(f"Total Sample Count: {self.__sampleCount}")

        if self.__outputConsoleMeasurements:
            print(" ".join(debug_parts))

        if not self.__startTriggerSet:
            self.__ClearOutput()

    def __processPacket(self, measurements):
        """Separates received packets into ZeroCal, RefCal, and measurement samples."""
        samples = []
        for measurement in measurements:
            self.dropped = measurement[0]
            numObs = measurement[2]
            offset = 3
            for _ in range(numObs):
                sample = measurement[offset : offset + 10]
                sample.append(measurement[-1])
                sampletype = sample[8] & 0x30

                if sampletype == ops.SampleType.ZeroCal:
                    self.__processZeroCal(sample)
                elif sampletype == ops.SampleType.refCal:
                    self.__processRefCal(sample)
                elif sampletype == ops.SampleType.Measurement:
                    samples.append(sample)

                offset += 10
        return samples

    def __startupCheck(self, verbose=False):
        """Verify the sample engine is setup to start."""
        if verbose:
            print("Verifying ready to start up\nCalibrating...")

        samples = [
            [0 for _ in range(self.__packetSize + 1)]
            for _ in range(self.bulkProcessRate)
        ]
        while not self.__isCalibrated() and self.__sampleCount < 20000:
            self.__sampleLoop(0, samples, 1)

        self.getSamples()

        if not self.__isCalibrated():
            print("Connection error, failed to calibrate after 20,000 samples")
            return False
        if not self.__channels[self.__triggerChannel]:
            print("Error: Trigger channel not enabled.")
            return False
        return True

    def __processZeroCal(self, meas):
        self.__mainCal.addZeroCal(meas[self.__mainCoarseIndex], True)
        self.__mainCal.addZeroCal(meas[self.__mainFineIndex], False)
        self.__usbCal.addZeroCal(meas[self.__usbCoarseIndex], True)
        self.__usbCal.addZeroCal(meas[self.__usbFineIndex], False)
        self.__auxCal.addZeroCal(meas[self.__auxCoarseIndex], True)
        self.__auxCal.addZeroCal(meas[self.__auxFineIndex], False)
        return True

    def __processRefCal(self, meas):
        self.__mainCal.addRefCal(meas[self.__mainCoarseIndex], True)
        self.__mainCal.addRefCal(meas[self.__mainFineIndex], False)
        self.__usbCal.addRefCal(meas[self.__usbCoarseIndex], True)
        self.__usbCal.addRefCal(meas[self.__usbFineIndex], False)
        self.__auxCal.addRefCal(meas[self.__auxCoarseIndex], True)
        self.__auxCal.addRefCal(meas[self.__auxFineIndex], False)
        return True

    def getSamples(self):
        """Returns samples as a list: [timestamp, main, usb, aux, mainVolts, usbVolts]."""
        return self.__arrangeSamples(exportAllIndices=True)

    def __outputToCSV(self):
        """Writes measurements periodically to a CSV file."""
        output = self.__arrangeSamples()
        if len(output) >= 3 and all(len(ch) > 0 for ch in output[:3]):
            self.__outputCheckNum += len(output[0])
            if self.__outputCheckNum > self.__granularity:
                num_rows = int(self.__outputCheckNum / self.__granularity)
                lines = [
                    ",".join(str(output[j][i]) for j in range(len(output))) + "\n"
                    for i in range(num_rows)
                ]
                self.__f.writelines(lines)
                self.__outputCheckNum %= self.__granularity

    def __arrangeSamples(self, exportAllIndices=False):
        """Arranges output lists for easier processing."""
        output = []

        times = [measurement for data in self.__timeStamps for measurement in data]
        output.append(times)
        self.__timeStamps = []

        channel_map = [
            (Channels.MainCurrent, self.__mainCurrent),
            (Channels.USBCurrent, self.__usbCurrent),
            (Channels.AuxCurrent, self.__auxCurrent),
            (Channels.MainVoltage, self.__mainVoltage),
            (Channels.USBVoltage, self.__usbVoltage),
        ]

        for channel_enum, data_list in channel_map:
            if self.__channels[channel_enum] or exportAllIndices:
                output.append([m for data in data_list for m in data])
            data_list.clear()

        return output

    def outputCSVHeaders(self):
        """Creates column headers in the CSV output file for enabled channels."""
        headers = [
            name
            for enabled, name in zip(self.__channels, self.__channelnames)
            if enabled
        ]
        if self.__f:
            self.__f.write(",".join(headers) + "\n")

    def __sampleLoop(self, S, samples, processRate, legacy_timestamp=False):
        buffer = self.monsoon.BulkRead()
        for start in range(0, len(buffer), 64):
            if self.__stopTriggerSet:
                break
            buf = buffer[start : start + 64]
            sample = self.monsoon.swizzlePacket(buf)
            numSamples = sample[2]

            if legacy_timestamp:
                sample.append(int(time.time()))
            else:
                sample.append(time.time() - self.__startTime)

            samples[S] = sample
            S += numSamples

            if S >= processRate:
                bulkPackets = self.__processPacket(samples)
                if bulkPackets:
                    self.__vectorProcess(bulkPackets)
                S = 0
        return S

    def __startSampling(
        self, samples=5000, granularity=1, legacy_timestamp=False, calTime=1250
    ):
        self.__Reset()
        self.__granularity = granularity
        self.__sampleLimit = samples
        sample_buffer = [
            [0 for _ in range(self.__packetSize + 1)]
            for _ in range(self.bulkProcessRate)
        ]
        S = 0
        csvOutThreshold = self.bulkProcessRate / 2
        self.__startTime = time.time()

        if self.__CSVOutEnable:
            self.outputCSVHeaders()

        self.monsoon.StartSampling(calTime, Triggers.SAMPLECOUNT_INFINITE)

        if not self.__startupCheck(False):
            self.monsoon.stopSampling()
            return False

        while not self.__stopTriggerSet:
            S = self.__sampleLoop(
                S, sample_buffer, self.bulkProcessRate, legacy_timestamp
            )
            if S >= csvOutThreshold and self.__CSVOutEnable and self.__startTriggerSet:
                self.__outputToCSV()
            if S == 0:
                sample_buffer = [
                    [0 for _ in range(self.__packetSize + 1)]
                    for _ in range(self.bulkProcessRate)
                ]

        self.monsoon.stopSampling()

        if self.__CSVOutEnable:
            self.__outputToCSV()
            self.disableCSVOutput()

    def startSampling(
        self, samples=5000, granularity=1, legacy_timestamp=False, calTime=1250
    ):
        if self.__errorMode == ErrorHandlingModes.off:
            self.__startSampling(samples, granularity, legacy_timestamp, calTime)
        else:
            try:
                self.__startSampling(samples, granularity, legacy_timestamp, calTime)
            except KeyboardInterrupt:
                print("Caught keyboard interrupt, test ending abruptly.")
                self.monsoon.stopSampling()
                if self.__CSVOutEnable:
                    self.__outputToCSV()
                    self.disableCSVOutput()
            except usb.core.USBError:
                print(
                    "Caught disconnection event. Test restarting with default parameters"
                )
                self.monsoon.Reconnect()
                self.monsoon.stopSampling()
                if self.__CSVOutEnable:
                    self.__outputToCSV()
                    self.disableCSVOutput()
                    self.enableCSVOutput(self.__outputFilename)
                self.startSampling(samples, granularity, legacy_timestamp, calTime)
            except Exception as e:
                print(f"Error: Exception caught ({e}). Test failed.")
                self.monsoon.stopSampling()
                if self.__CSVOutEnable:
                    self.__outputToCSV()
                    self.disableCSVOutput()
                raise Exception(e) from e

    def periodicStartSampling(self, calTime=1250):
        """Enters sample mode without active sample loops."""
        self.__Reset()
        self.__sampleLimit = Triggers.SAMPLECOUNT_INFINITE
        self.__granularity = 1

        if self.__CSVOutEnable:
            self.outputCSVHeaders()

        self.__startTime = time.time()
        self.monsoon.StartSampling(calTime, Triggers.SAMPLECOUNT_INFINITE)

        if not self.__startupCheck():
            self.monsoon.stopSampling()
            return False

        return self.getSamples()

    def periodicCollectSamples(self, samples=100, legacy_timestamp=False):
        """Collects latest measurements after calling periodicStartSampling()."""
        self.__sampleCount = 0
        self.__sampleLimit = samples
        self.__stopTriggerSet = False
        self.monsoon.BulkRead()  # Clear stale buffer
        sample_buffer = [[0 for _ in range(self.__packetSize + 1)]]

        while not self.__stopTriggerSet:
            self.__sampleLoop(0, sample_buffer, 1, legacy_timestamp)

        if self.__CSVOutEnable and self.__startTriggerSet:
            self.__outputToCSV()

        return self.getSamples()

    def periodicStopSampling(self, closeCSV=False):
        """Performs cleanup tasks when finished sampling."""
        if self.__CSVOutEnable and self.__startTriggerSet:
            self.__outputToCSV()
            if closeCSV:
                self.disableCSVOutput()
        self.monsoon.stopSampling()

class calibrationData(object):
    """
    Stores calibration data for every Monsoon channel.
    Uses a rolling queue of size self.calsToKeep to store the last x measurements.
    """

    def __init__(self, calsToKeep=5):
        self.calsToKeep = calsToKeep
        self.refCalFine = [0 for _ in range(self.calsToKeep)]
        self.refCalCoarse = [0 for _ in range(self.calsToKeep)]
        self.zeroCalFine = [0 for _ in range(self.calsToKeep)]
        self.zeroCalCoarse = [0 for _ in range(self.calsToKeep)]

        self.refCalFineIndex = 0
        self.zeroCalFineIndex = 0
        self.refCalCoarseIndex = 0
        self.zeroCalCoarseIndex = 0

        self.coarseRefCalibrated = False
        self.coarseZeroCalibrated = False
        self.fineRefCalibrated = False
        self.fineZeroCalibrated = False

    def clear(self):
        """Reset calibration arrays and status indicators."""
        self.refCalFine = [0 for _ in range(self.calsToKeep)]
        self.refCalCoarse = [0 for _ in range(self.calsToKeep)]
        self.zeroCalFine = [0 for _ in range(self.calsToKeep)]
        self.zeroCalCoarse = [0 for _ in range(self.calsToKeep)]

        self.refCalFineIndex = 0
        self.zeroCalFineIndex = 0
        self.refCalCoarseIndex = 0
        self.zeroCalCoarseIndex = 0

        self.coarseRefCalibrated = False
        self.coarseZeroCalibrated = False
        self.fineRefCalibrated = False
        self.fineZeroCalibrated = False

    def __getCal(self, cal_list):
        if self.calibrated():
            return sum(cal_list) / len(cal_list)
        else:
            raise ValueError("Attempted to get calibration data when not calibrated.")

    def calibrated(self):
        """Returns True if all four calibration channels have sufficient measurements."""
        return (
            self.coarseRefCalibrated
            and self.coarseZeroCalibrated
            and self.fineRefCalibrated
            and self.fineZeroCalibrated
        )

    def getRefCal(self, Coarse):
        """Get average reference calibration measurement."""
        cal_list = self.refCalCoarse if Coarse else self.refCalFine
        return self.__getCal(cal_list)

    def getZeroCal(self, Coarse):
        """Get average zero calibration value."""
        cal_list = self.zeroCalCoarse if Coarse else self.zeroCalFine
        return self.__getCal(cal_list)

    def __addCal(self, cal_list, value, index):
        cal_list[index] = value

    def addRefCal(self, value, Coarse):
        """Add reference calibration measurement."""
        if value != 0:
            if Coarse:
                self.__addCal(self.refCalCoarse, value, self.refCalCoarseIndex)
                self.refCalCoarseIndex += 1
                if self.refCalCoarseIndex >= self.calsToKeep:
                    self.coarseRefCalibrated = True
                    self.refCalCoarseIndex = 0
            else:
                self.__addCal(self.refCalFine, value, self.refCalFineIndex)
                self.refCalFineIndex += 1
                if self.refCalFineIndex >= self.calsToKeep:
                    self.fineRefCalibrated = True
                    self.refCalFineIndex = 0

    def addZeroCal(self, value, Coarse):
        """Add zero calibration measurement."""
        if value != 0:
            if Coarse:
                self.__addCal(self.zeroCalCoarse, value, self.zeroCalCoarseIndex)
                self.zeroCalCoarseIndex += 1
                if self.zeroCalCoarseIndex >= self.calsToKeep:
                    self.coarseZeroCalibrated = True
                    self.zeroCalCoarseIndex = 0
            else:
                self.__addCal(self.zeroCalFine, value, self.zeroCalFineIndex)
                self.zeroCalFineIndex += 1
                if self.zeroCalFineIndex >= self.calsToKeep:
                    self.fineZeroCalibrated = True
                    self.zeroCalFineIndex = 0

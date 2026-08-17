from multiprocessing import Process

from Monsoon import HVPM, LVPM, pmapi, sampleEngine
from Monsoon import Operations as op


def testHVPM(serialno=None, Protocol=None):
    HVMON = HVPM.Monsoon()
    HVMON.setup_usb(serialno, Protocol or pmapi.USB_protocol())
    print("HVPM Serial Number: " + repr(HVMON.getSerialNumber()))
    HVMON.fillStatusPacket()
    HVMON.setVout(3)
    HVengine = sampleEngine.SampleEngine(HVMON)
    HVengine.enableCSVOutput("HV Main Example.csv")
    HVengine.ConsoleOutput(True)
    numSamples = sampleEngine.triggers.SAMPLECOUNT_INFINITE  # Don't stop based on sample count, continue until the trigger conditions have been satisfied.
    HVengine.setStartTrigger(
        sampleEngine.triggers.GREATER_THAN, 0
    )  # Start when we exceed 0 s
    HVengine.setStopTrigger(
        sampleEngine.triggers.GREATER_THAN, 20
    )  # Stop when we exceed 5 s.
    HVengine.setTriggerChannel(
        sampleEngine.channels.timeStamp
    )  # Start and stop judged by the timestamp channel.
    HVengine.startSampling(numSamples)
    HVMON.closeDevice()


def testLVPM(serialno=None, Protcol=None):
    Mon = LVPM.Monsoon()
    Mon.setup_usb(serialno, Protcol or pmapi.USB_protocol())
    print("LVPM Serial number: " + repr(Mon.getSerialNumber()))
    Mon.fillStatusPacket()
    Mon.setVout(4.5)
    engine = sampleEngine.SampleEngine(Mon)
    engine.enableCSVOutput("Main Example.csv")
    engine.ConsoleOutput(True)
    # test main channels
    numSamples = sampleEngine.triggers.SAMPLECOUNT_INFINITE  # Don't stop based on sample count, continue until the trigger conditions have been satisfied.
    engine.setStartTrigger(
        sampleEngine.triggers.GREATER_THAN, 0
    )  # Start when we exceed 0 s
    engine.setStopTrigger(
        sampleEngine.triggers.GREATER_THAN, 5
    )  # Stop when we exceed 5 s.
    engine.setTriggerChannel(
        sampleEngine.channels.timeStamp
    )  # Start and stop judged by the timestamp channel.
    engine.startSampling(numSamples)

    # Disable Main channels
    engine.disableChannel(sampleEngine.channels.MainCurrent)
    engine.disableChannel(sampleEngine.channels.MainVoltage)

    engine.setStartTrigger(sampleEngine.triggers.GREATER_THAN, 0)
    engine.setStopTrigger(sampleEngine.triggers.GREATER_THAN, 10)
    engine.setTriggerChannel(sampleEngine.channels.timeStamp)
    # Take measurements from the USB Channel
    Mon.setVout(0)
    # Set USB Passthrough mode to 'on,' since it defaults to 'auto' and will turn off when sampling mode begins.
    Mon.setUSBPassthroughMode(op.USB_Passthrough.On)
    # Enable USB channels
    engine.enableChannel(sampleEngine.channels.USBCurrent)
    engine.enableChannel(sampleEngine.channels.USBVoltage)
    engine.enableCSVOutput("USB Test.csv")
    engine.startSampling(5000)

    # Enable every channel, take measurements
    engine.enableChannel(sampleEngine.channels.MainVoltage)
    engine.enableChannel(sampleEngine.channels.MainCurrent)
    # Enable Aux channel
    engine.enableChannel(sampleEngine.channels.AuxCurrent)
    Mon.setVout(2.5)
    engine.enableCSVOutput("All Test.csv")
    engine.startSampling(5000)

    # Enable every channel, take measurements, and retrieve them as a Python list.
    engine.disableCSVOutput()
    engine.startSampling(5000)
    engine.getSamples()
    Mon.closeDevice()


def droppedSamplesTest(ser=None, Prot=None):
    Mon = HVPM.Monsoon()
    Mon.setup_usb(ser, Prot or pmapi.USB_protocol())
    Mon.setVout(4.0)
    engine = sampleEngine.SampleEngine(Mon)
    # engine.enableCSVOutput(repr(ser) + ".csv")
    engine.ConsoleOutput(False)
    # test main channels
    engine.enableChannel(sampleEngine.channels.MainCurrent)
    numSamples = 1000000  # Don't stop based on sample count, continue until the trigger conditions have been satisfied.
    engine.setTriggerChannel(
        sampleEngine.channels.timeStamp
    )  # Start and stop judged by the timestamp channel.
    engine.startSampling(numSamples)
    samps = engine.getSamples()
    sampleCount = len(samps[0])
    print(
        repr(ser)
        + ": SampleCount: "
        + repr(sampleCount)
        + " Percent dropped: "
        + repr((engine.dropped / sampleCount) * 100)
    )


def multiHVPMTest(serialnos):
    for serial in serialnos:
        p = Process(
            target=droppedSamplesTest, args=(serial, pmapi.CPP_Backend_Protocol())
        )
        p.start()


# Unguarded upstream, so `import Monsoon.Main` -- or any tool that walked the package
# -- immediately forked four processes and went looking for four specific Power
# Monitors by serial number. Under a __main__ guard it is what it reads as: a manual
# smoke test someone runs on purpose.
if __name__ == "__main__":
    serialnos = [11500, 20019, 20486, 20487]
    multiHVPMTest(serialnos)
    testHVPM()

    # testLVPM(60001,pmapi.USB_protocol())
    # testHVPM(60000,pmapi.CPP_Backend_Protocol())

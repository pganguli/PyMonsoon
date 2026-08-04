from multiprocessing import Process

from Monsoon import HVPM, LVPM, pmapi, sampleEngine
from Monsoon import Operations as op


def testHVPM(serialno=None, Protocol=pmapi.USB_protocol()):
    HVMON = HVPM.Monsoon()
    HVMON.setup_usb(serialno, Protocol)
    print("HVPM Serial Number: " + repr(HVMON.getSerialNumber()))
    HVMON.fillStatusPacket()
    HVMON.setVout(3)

    HVengine = sampleEngine.SampleEngine(HVMON)
    HVengine.enableCSVOutput("HV Main Example.csv")
    HVengine.ConsoleOutput(True)

    numSamples = sampleEngine.triggers.SAMPLECOUNT_INFINITE
    HVengine.setStartTrigger(sampleEngine.triggers.GREATER_THAN, 0)
    HVengine.setStopTrigger(sampleEngine.triggers.GREATER_THAN, 20)
    HVengine.setTriggerChannel(sampleEngine.channels.timeStamp)

    HVengine.startSampling(numSamples)
    HVMON.closeDevice()


def testLVPM(serialno=None, Protocol=pmapi.USB_protocol()):
    Mon = LVPM.Monsoon()
    Mon.setup_usb(serialno, Protocol)
    print("LVPM Serial number: " + repr(Mon.getSerialNumber()))
    Mon.fillStatusPacket()
    Mon.setVout(4.5)

    engine = sampleEngine.SampleEngine(Mon)
    engine.enableCSVOutput("Main Example.csv")
    engine.ConsoleOutput(True)

    # Test main channels
    numSamples = sampleEngine.triggers.SAMPLECOUNT_INFINITE
    engine.setStartTrigger(sampleEngine.triggers.GREATER_THAN, 0)
    engine.setStopTrigger(sampleEngine.triggers.GREATER_THAN, 5)
    engine.setTriggerChannel(sampleEngine.channels.timeStamp)
    engine.startSampling(numSamples)

    # Disable Main channels
    engine.disableChannel(sampleEngine.channels.MainCurrent)
    engine.disableChannel(sampleEngine.channels.MainVoltage)

    engine.setStartTrigger(sampleEngine.triggers.GREATER_THAN, 0)
    engine.setStopTrigger(sampleEngine.triggers.GREATER_THAN, 10)
    engine.setTriggerChannel(sampleEngine.channels.timeStamp)

    # Take measurements from the USB Channel
    Mon.setVout(0)
    Mon.setUSBPassthroughMode(op.USB_Passthrough.On)

    engine.enableChannel(sampleEngine.channels.USBCurrent)
    engine.enableChannel(sampleEngine.channels.USBVoltage)
    engine.enableCSVOutput("USB Test.csv")
    engine.startSampling(5000)

    # Enable every channel, take measurements
    engine.enableChannel(sampleEngine.channels.MainVoltage)
    engine.enableChannel(sampleEngine.channels.MainCurrent)
    engine.enableChannel(sampleEngine.channels.AuxCurrent)
    Mon.setVout(2.5)
    engine.enableCSVOutput("All Test.csv")
    engine.startSampling(5000)

    # Enable every channel, take measurements as Python list
    engine.disableCSVOutput()
    engine.startSampling(5000)
    engine.getSamples()
    Mon.closeDevice()


def droppedSamplesTest(ser=None, Prot=pmapi.USB_protocol()):
    Mon = HVPM.Monsoon()
    Mon.setup_usb(ser, Prot)
    Mon.setVout(4.0)

    engine = sampleEngine.SampleEngine(Mon)
    engine.ConsoleOutput(False)
    engine.enableChannel(sampleEngine.channels.MainCurrent)

    numSamples = 1000000
    engine.setTriggerChannel(sampleEngine.channels.timeStamp)
    engine.startSampling(numSamples)

    samps = engine.getSamples()
    sampleCount = len(samps[0]) if samps and len(samps) > 0 else 0

    if sampleCount > 0:
        percent_dropped = (engine.dropped / sampleCount) * 100
        print(
            f"{ser}: SampleCount: {sampleCount} Percent dropped: {percent_dropped:.2f}%"
        )
    else:
        print(f"{ser}: No samples collected.")

    Mon.closeDevice()


def multiHVPMTest(serialnos):
    processes = []
    for serial in serialnos:
        p = Process(
            target=droppedSamplesTest, args=(serial, pmapi.CPP_Backend_Protocol())
        )
        p.start()
        processes.append(p)

    for p in processes:
        p.join()


if __name__ == "__main__":
    # --- Uncomment the test you want to run ---

    # For Low Voltage Power Monitor (LVPM):
    testLVPM()

    # For High Voltage Power Monitor (HVPM):
    # testHVPM()

    # For multi-device HVPM testing:
    # serialnos = [11500, 20019, 20486, 20487]
    # multiHVPMTest(serialnos)

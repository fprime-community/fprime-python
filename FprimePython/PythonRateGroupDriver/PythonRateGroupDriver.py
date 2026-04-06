""" PythonRateGroupDriver Python component implementation

This is the Python implementation for the PythonRateGroupDriver component. This class extends the auto-coded python base
class PythonRateGroupDriverBase that provides the necessary plumbing to connect to the C++ stub connected to the rest of
the F Prime topology.
"""
import fprime_py
from PythonRateGroupDriverBaseAc import PythonRateGroupDriverBase

import time

class PythonRateGroupDriver(PythonRateGroupDriverBase):
    """ Python implementation for the PythonRateGroupDriver component """

    def driveRateGroup(self, time_interval: fprime_py.Fw.TimeInterval):
        """ Drive the rate group driver at the intended rate """
        duration = time_interval.getInterval()
        # A CTRL-C will cause this while loop to exit
        try:
            while True:
                time.sleep(duration)
        except KeyboardInterrupt:
            print("CTRL-C received, stopping rate group driver")
    
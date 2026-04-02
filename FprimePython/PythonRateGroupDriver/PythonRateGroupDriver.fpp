module FprimePython {
    @ A rate-group driver for python applications
    @ fprime-python
    passive component PythonRateGroupDriver {
        import Drv.Tick

        ###############################################################################
        # Standard AC Ports: Required for Channels, Events, Commands, and Parameters  #
        ###############################################################################
        @ Port for requesting the current time
        time get port timeCaller

    }
}
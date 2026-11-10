module {{cookiecutter.component_namespace}} {
    @ {{cookiecutter.component_short_description}}
    @ fprime-python
    {{cookiecutter.component_kind}} component {{cookiecutter.component_name}} {
        @ Place-holder command: reports the greeting it is sent as a Hello event
        {% if cookiecutter.component_kind == "passive" %}sync{% else %}async{% endif %} command HELLO(
            greeting: string size 40 @< Greeting to report
        )

        @ Place-holder event: the greeting received by the HELLO command
        event Hello(
            greeting: string size 40 @< Greeting received
        ) severity activity high format "Hello: {}"

        @ Place-holder telemetry channel: count of HELLO commands received
        telemetry HelloCount: U32

        ###############################################################################
        # Standard AC Ports: Required for Channels, Events, Commands, and Parameters  #
        ###############################################################################
        @ Port for requesting the current time
        time get port timeCaller

        @ Port for sending command registrations
        command reg port cmdRegOut

        @ Port for receiving commands
        command recv port cmdIn

        @ Port for sending command responses
        command resp port cmdResponseOut

        @ Port for sending textual representation of events
        text event port logTextOut

        @ Port for sending events to downlink
        event port logOut

        @ Port for sending telemetry channels to downlink
        telemetry port tlmOut

        @ Port to return the value of a parameter
        param get port prmGetOut

        @ Port to set the value of a parameter
        param set port prmSetOut

    }
}

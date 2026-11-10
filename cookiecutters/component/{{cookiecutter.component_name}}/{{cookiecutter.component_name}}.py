""" {{cookiecutter.component_name}} Python component implementation

This is the Python implementation for the {{cookiecutter.component_name}} component. This class extends the auto-coded python base
class {{cookiecutter.component_name}}Base that provides the necessary plumbing to connect to the C++ stub connected to the rest of
the F Prime topology.

Each build writes {{cookiecutter.component_name}}.template.py next to this file with a stub for every handler in the model. Copy
the stubs of newly modeled handlers from there into this file.
"""
import fprime_py
from {{cookiecutter.component_name}}BaseAc import {{cookiecutter.component_name}}Base


class {{cookiecutter.component_name}}({{cookiecutter.component_name}}Base):
    """ Python implementation for the {{cookiecutter.component_name}} component """
    def __init__(self):
        """ Construct the component

        The component is constructed during the "init" phase when the component is originally called. During this phase
        the F Prime topology is not yet fully constructed, so only basic initialization should be done here.
        """
        super().__init__()
        self.hello_count = 0

    def HELLO_cmdHandler(self, opCode, cmdSeq, greeting):
        """ Handle the HELLO command """
        self.hello_count += 1
        self.log_ACTIVITY_HI_Hello(greeting)
        self.tlmWrite_HelloCount(self.hello_count)
        self.cmdResponse_out(opCode, cmdSeq, fprime_py.Fw.CmdResponse(fprime_py.Fw.CmdResponse.T.OK))

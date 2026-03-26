// ======================================================================
// \title FprimePython/PythonConsole/Console.cpp
// \brief posix implementation for Os::Console
// ======================================================================
#include <FprimePython/PythonConsole/Console.hpp>
#include <pybind11/pybind11.h>

namespace FprimePython {
namespace Console {

void PythonConsole::writeMessage(const CHAR* message, const FwSizeType size) {
    pybind11::gil_scoped_acquire acquire{};
    pybind11::print(message);
}

Os::ConsoleHandle* PythonConsole::getHandle() {
    return &this->m_handle;
}

}  // namespace Console
}  // namespace FprimePython
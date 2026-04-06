// ======================================================================
// \title Os/Posix/DefaultConsole.cpp
// \brief sets default Os::Console to posix implementation via linker
// ======================================================================
#include "Os/Console.hpp"
#include "Os/Delegate.hpp"
#include "FprimePython/PythonConsole/Console.hpp"

namespace Os {
ConsoleInterface* ConsoleInterface::getDelegate(ConsoleHandleStorage& aligned_new_memory,
                                                const ConsoleInterface* to_copy) {
    return Os::Delegate::makeDelegate<ConsoleInterface, FprimePython::Console::PythonConsole>(aligned_new_memory, to_copy);
}
}  // namespace Os

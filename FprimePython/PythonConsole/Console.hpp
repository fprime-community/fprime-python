// ======================================================================
// \title Os/Posix/Console.hpp
// \brief posix implementation for Os::Console, header and test definitions
// ======================================================================
#include <Os/Console.hpp>
#ifndef FPRIME_PYTHON_CONSOLE_HPP
#define FPRIME_PYTHON_CONSOLE_HPP

namespace FprimePython {
namespace Console {

//! ConsoleHandle class definition for posix implementations.
//!
struct PythonConsoleHandle : public Os::ConsoleHandle {};

//! \brief posix implementation of Os::ConsoleInterface
//!
//! Posix implementation of `ConsoleInterface` for use as a delegate class handling posix console operations. Posix
//! consoles write to either standard out or standard error. The default file descriptor used is standard out. This may
//! be changed by calling `setOutputStream`.
//!
class PythonConsole : public Os::ConsoleInterface {
  public:
    //! \brief constructor
    //!
    PythonConsole() = default;

    //! \brief copy constructor
    PythonConsole(const PythonConsole& other) = default;

    //! \brief assignment operator that copies the internal representation
    PythonConsole& operator=(const PythonConsole& other) = default;

    //! \brief destructor
    //!
    ~PythonConsole() override = default;

    // ------------------------------------
    // Functions overrides
    // ------------------------------------

    //! \brief write message to console
    //!
    //! Write a message to the console with a bounded size. This will use the active file descriptor as the output
    //! destination.
    //!
    //! \param message: raw message to write
    //! \param size: size of the message to write to the console
    void writeMessage(const CHAR* message, const FwSizeType size) override;

    //! \brief returns the raw console handle
    //!
    //! Gets the raw console handle from the implementation. Note: users must include the implementation specific
    //! header to make any real use of this handle. Otherwise it will be as an opaque type.
    //!
    //! \return raw console handle
    //!
    Os::ConsoleHandle* getHandle() override;

  private:
    //! File handle for PythonConsole
    PythonConsoleHandle m_handle;
};
}  // namespace Console
}  // namespace Posix

#endif  // FPRIME_PYTHON_CONSOLE_HPP

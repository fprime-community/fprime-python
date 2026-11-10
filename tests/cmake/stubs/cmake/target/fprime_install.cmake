# Stand-in for F Prime's cmake/target/fprime_install.cmake: installs one component to FPRIME_INSTALL_DEST
set(ENV{DESTDIR} "${FPRIME_INSTALL_DEST}")
set(CMAKE_INSTALL_PREFIX "/")
include("${FPRIME_BUILD_DIR}/cmake_install.cmake")

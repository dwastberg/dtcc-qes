cmake_minimum_required(VERSION 3.18)
project(dtcc_qes VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

find_package(Python 3.13 REQUIRED COMPONENTS Interpreter Development.Module)
execute_process(COMMAND "${Python_EXECUTABLE}" -m nanobind --cmake_dir
  OUTPUT_VARIABLE nanobind_ROOT OUTPUT_STRIP_TRAILING_WHITESPACE
  RESULT_VARIABLE DTCC_QES_NANOBIND_STATUS)
if(NOT DTCC_QES_NANOBIND_STATUS EQUAL 0)
  message(FATAL_ERROR "nanobind must be installed in the build environment")
endif()
find_package(nanobind CONFIG REQUIRED)

# Normal variables honour the embedding build without overwriting user caches.
set(QES_ENABLE_IO OFF)
set(QES_ENABLE_CUDA OFF)
set(QES_ENABLE_OPTIX OFF)
set(QES_BUILD_EXECUTABLES OFF)
set(QES_BUILD_EXAMPLES OFF)
set(QES_BUILD_PLUME OFF)
set(QES_BUILD_FIRE OFF)
set(ENABLE_OPENMP OFF)
add_subdirectory(QES-Public)
target_compile_definitions(qesutil PRIVATE NDEBUG)
target_compile_definitions(qeswindscore PRIVATE NDEBUG)

set(DTCC_QES_QES_REVISION "unknown" CACHE STRING "QES source revision (recorded in sdists)")
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/src/dtcc_qes/_qes_revision.txt")
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/src/dtcc_qes/_qes_revision.txt")
  file(STRINGS "${CMAKE_CURRENT_SOURCE_DIR}/src/dtcc_qes/_qes_revision.txt" DTCC_QES_QES_REVISION LIMIT_COUNT 1)
endif()
find_package(Git QUIET)
if(Git_FOUND AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/QES-Public/.git")
  execute_process(COMMAND "${GIT_EXECUTABLE}" -C "${CMAKE_CURRENT_SOURCE_DIR}/QES-Public" rev-parse HEAD
    OUTPUT_VARIABLE DTCC_QES_QES_REVISION OUTPUT_STRIP_TRAILING_WHITESPACE)
endif()

# Bindings contain no QES headers; only the audited bridge instantiates them.
add_library(qesbridge OBJECT src/cpp/build_info.cpp)
target_link_libraries(qesbridge PRIVATE qeswindscore)
target_compile_definitions(qesbridge PRIVATE NDEBUG DTCC_QES_QES_REVISION="${DTCC_QES_QES_REVISION}")
nanobind_add_module(_qes src/cpp/bindings.cpp $<TARGET_OBJECTS:qesbridge>)
target_link_libraries(_qes PRIVATE qeswindscore)
target_compile_definitions(_qes PRIVATE NDEBUG)
install(TARGETS _qes LIBRARY DESTINATION dtcc_qes)

add_custom_target(check_native_symbols
  COMMAND "${Python_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/check_native_symbols.py"
    --categories file_io io_libraries --
    $<TARGET_FILE:qesutil> $<TARGET_FILE:qeswindscore> $<TARGET_OBJECTS:qesbridge>
  DEPENDS qesutil qeswindscore qesbridge COMMAND_EXPAND_LISTS VERBATIM)

option(DTCC_QES_BUILD_TESTS "Build native checks for the I/O split" OFF)
if(DTCC_QES_BUILD_TESTS)
  enable_testing()
  # Make accidental includes fail even on developer machines that have the
  # optional libraries installed. A symbol audit alone misses unused headers.
  foreach(header netcdf netcdf.h gdal.h gdal_priv.h ogrsf_frmts.h cpl_conv.h)
    file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/noio-headers/${header}"
      "#error I/O library header included in QES_ENABLE_IO=OFF build\n")
  endforeach()
  target_include_directories(qesbuild BEFORE INTERFACE "${CMAKE_CURRENT_BINARY_DIR}/noio-headers")
  add_executable(check_noio tests/native/check_noio.cpp)
  target_compile_definitions(check_noio PRIVATE NDEBUG)
  # Force resolution of every core object, including objects the smoke module
  # does not yet use. This catches leaks across the I/O target boundary.
  if(APPLE)
    target_link_libraries(check_noio PRIVATE qeswindscore)
    target_link_options(check_noio PRIVATE "LINKER:-force_load,$<TARGET_FILE:qeswindscore>" "LINKER:-force_load,$<TARGET_FILE:qesutil>")
  elseif(UNIX)
    target_link_libraries(check_noio PRIVATE "-Wl,--whole-archive" qeswindscore qesutil "-Wl,--no-whole-archive")
  else()
    target_link_libraries(check_noio PRIVATE qeswindscore)
  endif()
  add_test(NAME noio_rejects_files COMMAND check_noio)
endif()

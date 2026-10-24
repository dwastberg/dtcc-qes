cmake_minimum_required(VERSION 3.18)
project(dtcc_qes VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
option(DTCC_QES_BUILD_TESTS "Build native embedding safety checks" OFF)
option(DTCC_QES_ENABLE_SANITIZERS "Enable AddressSanitizer and UndefinedBehaviorSanitizer" OFF)
set(DTCC_QES_OPENMP "AUTO" CACHE STRING "OpenMP CPU solver: OFF, AUTO, or ON")
set_property(CACHE DTCC_QES_OPENMP PROPERTY STRINGS OFF AUTO ON)
if(NOT DTCC_QES_OPENMP MATCHES "^(OFF|AUTO|ON)$")
  message(FATAL_ERROR "DTCC_QES_OPENMP must be OFF, AUTO, or ON")
endif()
set(ENABLE_OPENMP OFF)
if(DTCC_QES_OPENMP STREQUAL "ON")
  find_package(OpenMP REQUIRED COMPONENTS CXX)
  set(ENABLE_OPENMP ON)
elseif(DTCC_QES_OPENMP STREQUAL "AUTO")
  find_package(OpenMP QUIET COMPONENTS CXX)
  if(OpenMP_CXX_FOUND)
    set(ENABLE_OPENMP ON)
  endif()
endif()
message(STATUS "dtcc-qes OpenMP CPU solver: ${ENABLE_OPENMP} (requested ${DTCC_QES_OPENMP})")

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
add_subdirectory(QES-Public)
if(NOT CMAKE_BUILD_TYPE STREQUAL "Debug" AND NOT DTCC_QES_ENABLE_SANITIZERS)
  target_compile_definitions(qesbuild INTERFACE NDEBUG)
endif()
if(DTCC_QES_ENABLE_SANITIZERS)
  if(NOT CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang|AppleClang")
    message(FATAL_ERROR "Sanitizer checks require GCC or Clang")
  endif()
  target_compile_options(qesbuild INTERFACE -fsanitize=address,undefined -fno-omit-frame-pointer -UNDEBUG)
  target_link_options(qesbuild INTERFACE -fsanitize=address,undefined)
endif()

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
add_library(qesbridge OBJECT src/cpp/build_info.cpp src/cpp/qes_inputs.cpp
  src/cpp/log_sink.cpp src/cpp/wind_runner.cpp)
target_link_libraries(qesbridge PRIVATE qeswindscore)
target_compile_definitions(qesbridge PRIVATE DTCC_QES_QES_REVISION="${DTCC_QES_QES_REVISION}")
nanobind_add_module(_qes src/cpp/bindings.cpp $<TARGET_OBJECTS:qesbridge>)
target_link_libraries(_qes PRIVATE qeswindscore)
target_compile_definitions(_qes PRIVATE
  DTCC_QES_COMPILER_ID="${CMAKE_CXX_COMPILER_ID}"
  DTCC_QES_COMPILER_VERSION="${CMAKE_CXX_COMPILER_VERSION}"
  DTCC_QES_BUILD_TYPE="${CMAKE_BUILD_TYPE}")
if(NOT DTCC_QES_BUILD_TESTS AND NOT CMAKE_BUILD_TYPE STREQUAL "Debug")
  target_compile_definitions(_qes PRIVATE DTCC_QES_DISTRIBUTABLE_BUILD)
endif()
install(TARGETS _qes LIBRARY DESTINATION dtcc_qes)

add_custom_target(check_native_symbols
  COMMAND "${Python_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/check_native_symbols.py"
    $<TARGET_FILE:qesutil> $<TARGET_FILE:qeswindscore> $<TARGET_OBJECTS:qesbridge>
  DEPENDS qesutil qeswindscore qesbridge COMMAND_EXPAND_LISTS VERBATIM)

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
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/cases.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/make_native_fixture.py")
  execute_process(COMMAND "${Python_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/make_native_fixture.py"
    "${CMAKE_CURRENT_BINARY_DIR}/fixture.h" RESULT_VARIABLE DTCC_QES_FIXTURE_STATUS)
  if(NOT DTCC_QES_FIXTURE_STATUS EQUAL 0)
    message(FATAL_ERROR "Could not generate native fixture constants")
  endif()
  add_executable(check_safety tests/native/check_safety.cpp)
  target_include_directories(check_safety PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
  target_link_libraries(check_safety PRIVATE qeswindscore)
  foreach(mode success failures nonconvergence messages)
    add_test(NAME native_${mode} COMMAND check_safety ${mode})
  endforeach()
  find_package(Threads REQUIRED)
  add_executable(check_runner tests/native/check_runner.cpp $<TARGET_OBJECTS:qesbridge>)
  target_include_directories(check_runner PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src/cpp" "${CMAKE_CURRENT_BINARY_DIR}")
  target_link_libraries(check_runner PRIVATE qeswindscore Threads::Threads)
  add_test(NAME runner_lifecycle COMMAND check_runner)
  add_executable(check_physics tests/native/check_physics.cpp $<TARGET_OBJECTS:qesbridge>)
  target_include_directories(check_physics PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src/cpp" "${CMAKE_CURRENT_BINARY_DIR}")
  target_link_libraries(check_physics PRIVATE qeswindscore)
  add_test(NAME staggered_flux COMMAND check_physics)
  if(ENABLE_OPENMP)
    set_tests_properties(native_success native_failures native_nonconvergence
      native_messages runner_lifecycle staggered_flux PROPERTIES
      ENVIRONMENT "OMP_NUM_THREADS=2;OMP_DYNAMIC=FALSE")
    add_executable(check_openmp tests/native/check_openmp.cpp $<TARGET_OBJECTS:qesbridge>)
    target_include_directories(check_openmp PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src/cpp" "${CMAKE_CURRENT_BINARY_DIR}")
    target_link_libraries(check_openmp PRIVATE qeswindscore)
    foreach(threads 1 2 4)
      add_test(NAME openmp_${threads}_threads COMMAND check_openmp ${threads})
      set_tests_properties(openmp_${threads}_threads PROPERTIES TIMEOUT 60)
    endforeach()
  endif()
endif()

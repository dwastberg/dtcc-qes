cmake_minimum_required(VERSION 3.18)
# CMake >= 3.24 honours $<LINK_ONLY> in a target's own link libraries, which
# keeps the core's include paths away from the bindings (see _qes below).
if(POLICY CMP0131)
  cmake_policy(SET CMP0131 NEW)
endif()
project(dtcc_qes VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
option(DTCC_QES_BUILD_TESTS "Build native embedding safety checks" OFF)
option(DTCC_QES_ENABLE_SANITIZERS "Enable AddressSanitizer and UndefinedBehaviorSanitizer" OFF)
set(DTCC_QES_OPENMP "ON" CACHE STRING "OpenMP CPU solver: OFF, AUTO, or ON")
set_property(CACHE DTCC_QES_OPENMP PROPERTY STRINGS OFF AUTO ON)
if(NOT DTCC_QES_OPENMP MATCHES "^(OFF|AUTO|ON)$")
  message(FATAL_ERROR "DTCC_QES_OPENMP must be OFF, AUTO, or ON")
endif()
set(ENABLE_OPENMP OFF)
if(NOT DTCC_QES_OPENMP STREQUAL "OFF")
  # Homebrew's keg-only libomp is outside Apple Clang's normal search paths.
  # Keep explicit OpenMP package roots authoritative; let
  # FindOpenMP check the compiler, header and runtime together.
  if(APPLE AND CMAKE_CXX_COMPILER_ID MATCHES "Clang"
      AND NOT OpenMP_ROOT AND NOT DEFINED ENV{OpenMP_ROOT})
    find_path(DTCC_QES_LIBOMP_ROOT NAMES include/omp.h
      PATHS /opt/homebrew/opt/libomp /usr/local/opt/libomp NO_DEFAULT_PATH)
    if(DTCC_QES_LIBOMP_ROOT)
      set(OpenMP_ROOT "${DTCC_QES_LIBOMP_ROOT}")
    endif()
  endif()
  find_package(OpenMP QUIET COMPONENTS CXX)
  if(OpenMP_CXX_FOUND)
    set(ENABLE_OPENMP ON)
  elseif(DTCC_QES_OPENMP STREQUAL "ON")
    message(FATAL_ERROR
      "OpenMP is required by default. Install an OpenMP-capable compiler/runtime "
      "(on macOS: brew install libomp). For a custom installation, set OpenMP_ROOT. "
      "To explicitly build the serial solver, set -DDTCC_QES_OPENMP=OFF.")
  else()
    message(WARNING "OpenMP was not found; explicit AUTO mode selects the serial CPU solver")
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

# Vendored QES no-I/O CPU core (qesbuild, qesutil, qeswindscore).
add_subdirectory(src/qes_core)
# Pin the compiler's existing contraction mode, including caller-supplied flags.
# Do not impose a new cross-compiler numerical trajectory during the refactor.
set(DTCC_QES_FP_CONTRACT "compiler-default-unverified")
if(CMAKE_CXX_COMPILER_ID MATCHES "^(AppleClang|Clang|GNU)$")
  file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/fp_contract_probe.cpp" "// compiler option probe\n")
  string(TOUPPER "${CMAKE_BUILD_TYPE}" DTCC_QES_CONFIG)
  separate_arguments(DTCC_QES_PROBE_FLAGS NATIVE_COMMAND
    "${CMAKE_CXX_FLAGS} ${CMAKE_CXX_FLAGS_${DTCC_QES_CONFIG}}")
  if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
    set(DTCC_QES_PROBE_OPTIONS -Q --help=optimizers)
  else()
    set(DTCC_QES_PROBE_OPTIONS "-###")
  endif()
  execute_process(COMMAND "${CMAKE_CXX_COMPILER}" ${DTCC_QES_PROBE_FLAGS}
    -std=c++17 ${DTCC_QES_PROBE_OPTIONS} -c "${CMAKE_CURRENT_BINARY_DIR}/fp_contract_probe.cpp"
    -o "${CMAKE_CURRENT_BINARY_DIR}/fp_contract_probe.o"
    OUTPUT_VARIABLE DTCC_QES_FP_OUT ERROR_VARIABLE DTCC_QES_FP_ERR
    RESULT_VARIABLE DTCC_QES_FP_STATUS)
  if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
    string(REGEX MATCH "-ffp-contract=[^ \r\n]*[ \t]+(fast|on|off)"
      DTCC_QES_FP_MATCH "${DTCC_QES_FP_OUT}${DTCC_QES_FP_ERR}")
  else()
    string(REGEX MATCH "-ffp-contract=(fast|on|off)"
      DTCC_QES_FP_MATCH "${DTCC_QES_FP_OUT}${DTCC_QES_FP_ERR}")
  endif()
  if(NOT DTCC_QES_FP_STATUS EQUAL 0 OR NOT DTCC_QES_FP_MATCH)
    message(FATAL_ERROR "Cannot determine the compiler's current floating-point contraction mode")
  endif()
  set(DTCC_QES_FP_CONTRACT "${CMAKE_MATCH_1}")
  target_compile_options(qesbuild INTERFACE "-ffp-contract=${DTCC_QES_FP_CONTRACT}")
endif()
target_compile_definitions(qesbridge PRIVATE DTCC_QES_FP_CONTRACT="${DTCC_QES_FP_CONTRACT}")
message(STATUS "dtcc-qes floating-point contraction: ${DTCC_QES_FP_CONTRACT}")
# A policy is qualified against its implementation AND arithmetic build. Keep
# the expected identity in a separate, excluded header to avoid a hash cycle.
file(GLOB_RECURSE DTCC_QES_POLICY_INPUTS CONFIGURE_DEPENDS
  "${CMAKE_CURRENT_SOURCE_DIR}/src/qes_core/*.h" "${CMAKE_CURRENT_SOURCE_DIR}/src/qes_core/*.cpp"
  "${CMAKE_CURRENT_SOURCE_DIR}/src/cpp/*.h" "${CMAKE_CURRENT_SOURCE_DIR}/src/cpp/*.cpp")
list(FILTER DTCC_QES_POLICY_INPUTS EXCLUDE REGEX "/pedestrian_qualification\\.h$")
list(APPEND DTCC_QES_POLICY_INPUTS "${CMAKE_CURRENT_SOURCE_DIR}/CMakeLists.txt"
  "${CMAKE_CURRENT_SOURCE_DIR}/src/qes_core/CMakeLists.txt")
list(SORT DTCC_QES_POLICY_INPUTS)
set(DTCC_QES_POLICY_IDENTITY "${CMAKE_CXX_COMPILER_ID}:${CMAKE_CXX_COMPILER_VERSION}:${CMAKE_BUILD_TYPE}:${CMAKE_CXX_FLAGS}:${CMAKE_CXX_FLAGS_${DTCC_QES_CONFIG}}:fp=${DTCC_QES_FP_CONTRACT}\n")
foreach(DTCC_QES_POLICY_INPUT IN LISTS DTCC_QES_POLICY_INPUTS)
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${DTCC_QES_POLICY_INPUT}")
  file(SHA256 "${DTCC_QES_POLICY_INPUT}" DTCC_QES_POLICY_SHA)
  file(RELATIVE_PATH DTCC_QES_POLICY_REL "${CMAKE_CURRENT_SOURCE_DIR}" "${DTCC_QES_POLICY_INPUT}")
  string(APPEND DTCC_QES_POLICY_IDENTITY "${DTCC_QES_POLICY_REL} ${DTCC_QES_POLICY_SHA}\n")
endforeach()
string(SHA256 DTCC_QES_POLICY_REVISION "${DTCC_QES_POLICY_IDENTITY}")
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/solver-policy-identity.txt" "${DTCC_QES_POLICY_IDENTITY}")
target_compile_definitions(qesbridge PRIVATE DTCC_QES_POLICY_REVISION="${DTCC_QES_POLICY_REVISION}")
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

# The QES-Public fork commit the vendored sources were taken from.
set(DTCC_QES_QES_REVISION "unknown" CACHE STRING "QES source revision (recorded in sdists)")
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/src/dtcc_qes/_qes_revision.txt")
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/src/dtcc_qes/_qes_revision.txt")
  file(STRINGS "${CMAKE_CURRENT_SOURCE_DIR}/src/dtcc_qes/_qes_revision.txt" DTCC_QES_QES_REVISION LIMIT_COUNT 1)
endif()

# Bindings contain no QES headers; only the audited bridge (qesbridge) instantiates them.
# LINK_ONLY keeps the core's include paths away from bindings.cpp, so a QES
# include there fails to compile instead of relying on convention.
target_compile_definitions(qesbridge PRIVATE DTCC_QES_QES_REVISION="${DTCC_QES_QES_REVISION}")
nanobind_add_module(_qes src/cpp/bindings.cpp $<TARGET_OBJECTS:qesbridge>)
target_link_libraries(_qes PRIVATE dtcc_qes_api $<LINK_ONLY:qeswindscore>)
if(DTCC_QES_ENABLE_SANITIZERS)
  target_compile_options(_qes PRIVATE -fsanitize=address,undefined -fno-omit-frame-pointer)
endif()
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
  add_test(NAME noio_core COMMAND check_noio)
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
  target_include_directories(check_runner PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
  target_link_libraries(check_runner PRIVATE dtcc_qes_internal Threads::Threads)
  add_test(NAME runner_lifecycle COMMAND check_runner)
  add_executable(check_contacts tests/native/check_contacts.cpp $<TARGET_OBJECTS:qesbridge>)
  target_link_libraries(check_contacts PRIVATE dtcc_qes_internal)
  add_test(NAME building_contacts COMMAND check_contacts)
  add_executable(check_physics tests/native/check_physics.cpp $<TARGET_OBJECTS:qesbridge>)
  target_include_directories(check_physics PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
  target_link_libraries(check_physics PRIVATE dtcc_qes_internal)
  add_test(NAME staggered_flux COMMAND check_physics)
  add_executable(check_turbulence tests/native/check_turbulence.cpp $<TARGET_OBJECTS:qesbridge>)
  target_link_libraries(check_turbulence PRIVATE dtcc_qes_internal)
  foreach(mode low_top ref_in_top_cell ref_above_top reference_boundary methods ownership references lifecycle
               rotation rotation_fallback calm validity building_validity wall_thin wall_upper_bound
               wall_geometry wall_nonuniform wall_transition wall_underside wall_empty
               flat_analytic bridge_calm scaling repeat wall_distance margin bridge_methods invalid_stress)
    add_test(NAME native_turbulence_${mode} COMMAND check_turbulence ${mode})
    set_tests_properties(native_turbulence_${mode} PROPERTIES
      ENVIRONMENT "OMP_NUM_THREADS=2;OMP_DYNAMIC=FALSE" TIMEOUT 60)
  endforeach()
  add_executable(check_vertical_grid tests/native/check_vertical_grid.cpp $<TARGET_OBJECTS:qesbridge>)
  target_link_libraries(check_vertical_grid PRIVATE dtcc_qes_internal)
  add_test(NAME explicit_vertical_grid COMMAND check_vertical_grid)
  add_executable(check_profiles tests/native/check_profiles.cpp $<TARGET_OBJECTS:qesbridge>)
  target_link_libraries(check_profiles PRIVATE dtcc_qes_internal)
  add_test(NAME background_profiles COMMAND check_profiles)
  set_tests_properties(background_profiles PROPERTIES TIMEOUT 60 ENVIRONMENT "OMP_NUM_THREADS=2;OMP_DYNAMIC=FALSE")
  add_executable(check_precision tests/native/check_precision.cpp $<TARGET_OBJECTS:qesbridge>)
  target_link_libraries(check_precision PRIVATE dtcc_qes_internal)
  add_test(NAME precision_solver COMMAND check_precision)
  add_executable(check_solver_phases tests/native/check_solver_phases.cpp $<TARGET_OBJECTS:qesbridge>)
  target_link_libraries(check_solver_phases PRIVATE dtcc_qes_internal)
  add_test(NAME solver_phases COMMAND check_solver_phases)
  add_executable(check_condition_mask tests/native/check_condition_mask.cpp $<TARGET_OBJECTS:qesbridge>)
  target_link_libraries(check_condition_mask PRIVATE dtcc_qes_internal)
  add_test(NAME condition_mask COMMAND check_condition_mask)
  set_tests_properties(condition_mask PROPERTIES TIMEOUT 60)
  add_executable(check_equation_residual tests/native/check_equation_residual.cpp $<TARGET_OBJECTS:qesbridge>)
  target_link_libraries(check_equation_residual PRIVATE dtcc_qes_internal)
  add_test(NAME equation_residual COMMAND check_equation_residual)
  set_tests_properties(equation_residual PROPERTIES TIMEOUT 60)
  add_executable(solver_numerics_probe tools/solver_numerics_probe.cpp $<TARGET_OBJECTS:qesbridge>)
  target_link_libraries(solver_numerics_probe PRIVATE dtcc_qes_internal)
  add_executable(check_monitor tests/native/check_monitor.cpp $<TARGET_OBJECTS:qesbridge>)
  target_link_libraries(check_monitor PRIVATE dtcc_qes_internal)
  add_test(NAME solver_monitor COMMAND check_monitor)
  set_tests_properties(solver_monitor PROPERTIES TIMEOUT 60)
  add_executable(check_solver_control tests/native/check_solver_control.cpp $<TARGET_OBJECTS:qesbridge>)
  target_link_libraries(check_solver_control PRIVATE dtcc_qes_internal)
  add_test(NAME solver_control COMMAND check_solver_control)
  set_tests_properties(solver_control PROPERTIES TIMEOUT 60 ENVIRONMENT "OMP_NUM_THREADS=2;OMP_DYNAMIC=FALSE")
  add_executable(check_pedestrian_policy tests/native/check_pedestrian_policy.cpp $<TARGET_OBJECTS:qesbridge>)
  target_link_libraries(check_pedestrian_policy PRIVATE dtcc_qes_internal)
  add_test(NAME pedestrian_policy COMMAND check_pedestrian_policy)
  set_tests_properties(pedestrian_policy PROPERTIES TIMEOUT 60 ENVIRONMENT "OMP_NUM_THREADS=2;OMP_DYNAMIC=FALSE")
  add_executable(solver_monitor_probe tools/solver_monitor_probe.cpp $<TARGET_OBJECTS:qesbridge>)
  target_link_libraries(solver_monitor_probe PRIVATE dtcc_qes_internal)
  set_tests_properties(solver_phases PROPERTIES TIMEOUT 60)
  # Opt-in numerical study; deliberately excluded from routine CTest workloads.
  add_executable(vertical_grid_study tools/vertical_grid_study.cpp
    tools/vertical_grid_diagnostics.cpp $<TARGET_OBJECTS:qesbridge>)
  target_link_libraries(vertical_grid_study PRIVATE dtcc_qes_internal)
  add_test(NAME study_sampler COMMAND vertical_grid_study --self-test)
  add_test(NAME study_solver_diagnostics COMMAND vertical_grid_study --diagnostics-self-test)
  if(ENABLE_OPENMP)
    set_tests_properties(native_success native_failures native_nonconvergence
      native_messages runner_lifecycle staggered_flux explicit_vertical_grid precision_solver PROPERTIES
      ENVIRONMENT "OMP_NUM_THREADS=2;OMP_DYNAMIC=FALSE")
    add_executable(check_openmp tests/native/check_openmp.cpp $<TARGET_OBJECTS:qesbridge>)
    target_include_directories(check_openmp PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
    target_link_libraries(check_openmp PRIVATE dtcc_qes_internal)
    foreach(threads 1 2 4)
      add_test(NAME openmp_${threads}_threads COMMAND check_openmp ${threads})
      set_tests_properties(openmp_${threads}_threads PROPERTIES TIMEOUT 60)
    endforeach()
  endif()
endif()

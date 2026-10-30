# Vendored QES-Winds no-I/O CPU core, driven from in-memory inputs; see
# PROVENANCE.md. GPL-3.0; see LICENSE.
add_library(qesbuild INTERFACE)
target_compile_features(qesbuild INTERFACE cxx_std_17)
target_compile_definitions(qesbuild INTERFACE QES_VERSION_INFO="v2.3.1")
target_include_directories(qesbuild INTERFACE "${CMAKE_CURRENT_SOURCE_DIR}")
if(ENABLE_OPENMP)
  find_package(OpenMP REQUIRED COMPONENTS CXX)
  target_link_libraries(qesbuild INTERFACE OpenMP::OpenMP_CXX)
endif()

add_library(qesutil STATIC
  util/QESLog.cpp util/BVH.cpp util/HitRecord.cpp
  util/Mesh.cpp util/Triangle.cpp util/Ray.cpp util/SphereDirections.cpp)
target_link_libraries(qesutil PUBLIC qesbuild)
target_include_directories(qesutil PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/util")
set_target_properties(qesutil PROPERTIES POSITION_INDEPENDENT_CODE ON)

add_library(qeswindscore STATIC
  qes/Domain.cpp
  winds/Cell.cpp winds/CutCell.cpp winds/CutBuilding.cpp
  winds/LocalMixingDefault.cpp winds/LocalMixingSerial.cpp winds/LocalMixingOptix.cpp
  winds/PolyBuilding.cpp
  solver/solver.cpp solver/cpu_float32.cpp solver/cpu_float64.cpp
  winds/TURBGeneralData.cpp winds/TURBWall.cpp winds/TURBWallBuilding.cpp winds/TURBWallTerrain.cpp
  winds/LogProfile.cpp
  winds/WINDSGeneralData.cpp winds/Wall.cpp winds/UpwindCavity.cpp winds/NonLocalMixing.cpp
  winds/PolygonWake.cpp winds/StreetCanyon.cpp winds/StreetCanyonModified.cpp winds/Sidewall.cpp
  winds/Rooftop.cpp)
target_link_libraries(qeswindscore PUBLIC qesutil)
target_include_directories(qeswindscore PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/winds")
set_target_properties(qeswindscore PROPERTIES POSITION_INDEPENDENT_CODE ON)

# dtcc layer. dtcc/api holds the QES-free headers seen by the Python bindings;
# dtcc holds the bridge that drives the core. Tests and tools use both.
add_library(dtcc_qes_api INTERFACE)
target_include_directories(dtcc_qes_api INTERFACE "${CMAKE_CURRENT_SOURCE_DIR}/dtcc/api")
add_library(dtcc_qes_internal INTERFACE)
target_include_directories(dtcc_qes_internal INTERFACE "${CMAKE_CURRENT_SOURCE_DIR}/dtcc")
target_link_libraries(dtcc_qes_internal INTERFACE dtcc_qes_api qeswindscore)
add_library(qesbridge OBJECT dtcc/build_info.cpp dtcc/model_inputs.cpp dtcc/divergence.cpp dtcc/monitor.cpp dtcc/solver_control.cpp
  dtcc/log_sink.cpp dtcc/wind_runner.cpp dtcc/turbulence.cpp)
target_link_libraries(qesbridge PRIVATE dtcc_qes_internal)

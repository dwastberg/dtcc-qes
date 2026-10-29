/****************************************************************************
 * Copyright (c) 2025 University of Utah
 * Copyright (c) 2025 University of Minnesota Duluth
 *
 * Copyright (c) 2025 Behnam Bozorgmehr
 * Copyright (c) 2025 Jeremy A. Gibbs
 * Copyright (c) 2025 Fabien Margairaz
 * Copyright (c) 2025 Eric R. Pardyjak
 * Copyright (c) 2025 Zachary Patterson
 * Copyright (c) 2025 Rob Stoll
 * Copyright (c) 2025 Lucas Ulmer
 * Copyright (c) 2025 Pete Willemsen
 *
 * This file is part of QES-Winds
 *
 * GPL-3.0 License
 *
 * QES-Winds is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, version 3 of the License.
 *
 * QES-Winds is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with QES-Winds. If not, see <https://www.gnu.org/licenses/>.
 ****************************************************************************/

/** @file QESout.cpp */


#include "util/QESLog.h"
#include "QESout.h"

namespace QESout {
namespace {
  bool verbose_flag = false;
}
void splashScreen()
{
  qes::log::info() << "###################################################################" << std::endl;
  qes::log::info() << "#                                                                 #" << std::endl;
  qes::log::info() << "#                        Welcome to QES                           #" << std::endl;
  qes::log::info() << "#                                                                 #" << std::endl;
  qes::log::info() << "###################################################################" << std::endl;
  qes::log::info() << "Version: " << QES_VERSION_INFO << std::endl;// QES_VERSION_INFO comes from CMakeLists.txt
#ifdef HAS_CUDA
  qes::log::info() << "* CUDA support available!" << std::endl;
#else
  qes::log::info() << "* No CUDA support - CPU Only Computations!" << std::endl;
#endif

#ifdef HAS_OPTIX
  qes::log::info() << "* OptiX is available!" << std::endl;
#endif

#ifdef _OPENMP
  qes::log::info() << "* OpenMP is available!" << std::endl;
#endif


#ifdef HAS_CUDA
  qes::log::info() << "------------------------------------------------------------------" << std::endl;
  int deviceCount = 0;
  cudaError_t error_id = cudaGetDeviceCount(&deviceCount);

  if (error_id != cudaSuccess) {
    qes::log::error() << "\n===================================================================" << std::endl;
    qes::log::error() << "[ERROR]\t cudaGetDeviceCount returned "
              << static_cast<int>(error_id) << "\n\t-> "
              << cudaGetErrorString(error_id) << std::endl;
    { std::ostringstream message; message << "===================================================================" << std::endl; throw qes::InputError(message.str()); }
  }

  // This function call returns 0 if there are no CUDA capable devices.
  if (deviceCount == 0) {
    qes::log::warning() << "[!! WARNING !!]\t There are no available device(s) that support CUDA\n";
  } else {
    qes::log::info() << "[CUDA]\t Detected " << deviceCount << " CUDA Capable device(s)" << std::endl;
    int dev, driverVersion = 0, runtimeVersion = 0;

    for (dev = 0; dev < deviceCount; ++dev) {

      cudaSetDevice(dev);

      cudaDeviceProp deviceProp;
      cudaGetDeviceProperties(&deviceProp, dev);

      qes::log::info() << "\t Device " << dev << ": " << deviceProp.name << std::endl;

      // Console log
      cudaDriverGetVersion(&driverVersion);
      cudaRuntimeGetVersion(&runtimeVersion);
      qes::log::info() << "\t | CUDA Driver Version / Runtime Version: "
                << driverVersion / 1000 << "." << (driverVersion % 100) / 10 << " / "
                << runtimeVersion / 1000 << "." << (runtimeVersion % 100) / 10 << std::endl;

      qes::log::info() << "\t | CUDA Capability Major/Minor version number: "
                << deviceProp.major << "." << deviceProp.minor << std::endl;

      char msg[256];
#if defined(WIN32) || defined(_WIN32) || defined(WIN64) || defined(_WIN64)
      sprintf_s(msg, sizeof(msg),
                "\t | Total amount of global memory: %.0f MBytes "
                "(%llu bytes)\n",
                static_cast<float>(deviceProp.totalGlobalMem / 1048576.0f),
                (unsigned long long)deviceProp.totalGlobalMem);
#else
      snprintf(msg, sizeof(msg),
               "\t | Total amount of global memory: %.0f MBytes "
               "(%llu bytes)\n",
               static_cast<float>(deviceProp.totalGlobalMem / 1048576.0f),
               (unsigned long long)deviceProp.totalGlobalMem);
#endif
      qes::log::info() << msg;

      //    qes::log::writef(qes::log::Level::info, "  (%2d) Multiprocessors, (%3d) CUDA Cores/MP:     %d CUDA Cores\n",
      //           deviceProp.multiProcessorCount,
      //           _ConvertSMVer2Cores(deviceProp.major, deviceProp.minor),
      //           _ConvertSMVer2Cores(deviceProp.major, deviceProp.minor) *
      //           deviceProp.multiProcessorCount);

      qes::log::info() << "\t | GPU Max Clock rate:  "
                << deviceProp.clockRate * 1e-3f << " MHz ("
                << deviceProp.clockRate * 1e-6f << " GHz)" << std::endl;

      qes::log::info() << "\t | PCI: BusID=" << deviceProp.pciBusID << ", "
                << "DeviceID=" << deviceProp.pciDeviceID << ", "
                << "DomainID=" << deviceProp.pciDomainID << std::endl;
    }
  }
#endif

  qes::log::info() << "###################################################################" << std::endl;
}


[[noreturn]] void error(std::string out)
{
  throw qes::RuntimeError(out);
}


void warning(std::string out)
{
  qes::log::warning() << out << std::endl;
}

void setVerbose()
{
  verbose_flag = true;
}

void verbose(std::string out)
{
  if (verbose_flag)
    qes::log::debug() << out << std::endl;
}
}// namespace QESout


// //////////////////////////////////////////////////
//
// IMPORTANT:  Keep the code below --Pete W
// The following code is needed to build in flags for the
// sanitizer that will allow CUDA to be run with the sanitizer
// checks in place. Without this function callback, these
// options needs to be set on the command line when the
// executable is called. For example,
// ASAN_OPTIONS=protect_shadow_gap=0:replace_intrin=0:detect_leaks=0 ./myExec
//
// Building the options in, as done below allows us to run the executables
// cleanly without having to type what is above.
//
#if defined(HAS_CUDA) && defined(__SANITIZE_ADDRESS__)
#ifdef __cplusplus
extern "C"
#endif
  const char *
  __asan_default_options()
{
  return "protect_shadow_gap=0:replace_intrin=0:detect_leaks=0";
}
#endif
// //////////////////////////////////////////////////

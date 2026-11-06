"""Keep device implementations out until a future backend is explicitly designed."""

from pathlib import Path
import io
import tarfile
import zipfile

import pytest

from fixtures.support import load_tool


ROOT = Path(__file__).resolve().parents[1]
artifacts = load_tool("cpu_only_artifacts", ROOT / "tools/check_artifacts.py")
symbols = load_tool("cpu_only_symbols", ROOT / "tools/check_native_symbols.py")


def test_runtime_source_and_build_are_cpu_only():
    paths = [p for p in (ROOT / "src").rglob("*") if p.is_file()]
    paths += [ROOT / "CMakeLists.txt", ROOT / "pyproject.toml"]
    artifacts.check_cpu_only_files(
        [p.relative_to(ROOT).as_posix() for p in paths],
        lambda name: (ROOT / name).read_bytes(),
    )


@pytest.mark.parametrize("name", [
    "src/kernel.cu", "src/kernel.cuh", "dtcc_qes/kernel.ptx",
    "dtcc_qes/kernel.cubin", "dtcc_qes/kernel.fatbin", "src/kernel.cl",
    "src/kernel.metal", "src/kernel.spv", "src/Solver_GPU.cpp",
    "dtcc_qes/libcudart.so", "src/LocalMixingOptix.h",
])
def test_rejects_device_files(name):
    with pytest.raises(ValueError, match="GPU file"):
        artifacts.check_cpu_only_files([name], lambda _: b"")


@pytest.mark.parametrize("content", [
    "project(example LANGUAGES CXX CUDA)", "find_package(CUDAToolkit)",
    'option(DTCC_QES_GPU "Device backend" OFF)',
    "#ifdef HAS_CUDA", "#include <CL/cl.h>\nclCreateContext();",
    "#include <optix.h>", "__global__ void project();", "hipMalloc(&p, n);",
    "#pragma omp target teams distribute parallel for", "import cupy.cuda",
    "#include <Metal/Metal.hpp>", "sycl::queue q;",
    "#include <CL/cl.h>", "#include <hip/hip_runtime.h>", "#include <thrust/device_vector.h>",
    "#pragma acc parallel loop",
])
def test_rejects_device_implementation_or_build_hook(content):
    with pytest.raises(ValueError, match="GPU code/build hook"):
        artifacts.check_cpu_only_files(["src/backend.cpp"], lambda _: content.encode())


def test_accepts_cpu_openmp_and_preserves_provenance_text():
    files = {
        "src/backend.cpp": b"#pragma omp parallel for\nnb::device::cpu;",
        "src/PROVENANCE.md": b"CUDA and OptiX were removed from the runtime.",
        "CMakeLists.txt": b"project(dtcc_qes LANGUAGES CXX)\nfind_package(OpenMP)",
    }
    artifacts.check_cpu_only_files(files, files.__getitem__)


def test_wheel_audit_rejects_device_payload(tmp_path):
    path = tmp_path / "device.whl"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("dtcc_qes/kernel.ptx", "")
    with pytest.raises(ValueError, match="GPU file"):
        artifacts.check_wheel(path)


def test_sdist_audit_rejects_device_build_hook(tmp_path):
    path = tmp_path / "device.tar.gz"
    content = b"find_package(CUDAToolkit)"
    with tarfile.open(path, "w:gz") as archive:
        entry = tarfile.TarInfo("dtcc-qes/CMakeLists.txt")
        entry.size = len(content)
        archive.addfile(entry, io.BytesIO(content))
    with pytest.raises(ValueError, match="GPU code/build hook"):
        artifacts.check_sdist(path)


@pytest.mark.parametrize("symbol", [
    "_cudaMalloc", "__cudaRegisterFatBinary", "cuLaunchKernel", "cublasCreate_v2",
    "cufftExecC2C", "curandGenerate", "cusparseCreate", "nvrtcCompileProgram",
    "optixInit", "hipMalloc", "clCreateContext", "vkCreateInstance", "sycl::queue::wait()",
])
def test_rejects_device_linkage(symbol):
    assert "gpu" in symbols.categories_for(symbol)

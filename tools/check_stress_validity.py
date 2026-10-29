"""Compare the QES-free C++ stress classifier with NumPy's eigensolver."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
PROBE = r"""
#include "stress_validity.h"
#include <iomanip>
#include <iostream>
int main() {
  dtcc_qes::StressTensor stress;
  std::cout << std::setprecision(17);
  while (std::cin >> stress[0] >> stress[1] >> stress[2]
                  >> stress[3] >> stress[4] >> stress[5]) {
    const auto result = dtcc_qes::stress_validity(stress);
    std::cout << result.valid << ' ' << result.minimum_eigenvalue << ' '
              << result.spectral_radius << ' ' << result.tolerance << '\n';
  }
}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20261027)
    parser.add_argument("--compiler", default="c++")
    args = parser.parse_args()
    if args.cases < 1:
        parser.error("--cases must be positive")

    rng = np.random.default_rng(args.seed)
    count, half = args.cases, args.cases // 2
    basis, _ = np.linalg.qr(rng.normal(size=(count, 3, 3)))
    eigenvalues = rng.uniform(-3, 3, size=(count, 3))
    eigenvalues[:half] = rng.uniform(0.5, 3, size=(half, 3))
    eigenvalues[:half, 0] = (rng.uniform(-2, 2, size=half)
                             * 32 * np.finfo(np.float32).eps * eigenvalues[:half, 2])
    matrices = np.einsum("nik,nk,njk->nij", basis, eigenvalues, basis)
    matrices *= 10**rng.uniform(-30, 30, size=(count, 1, 1))
    # The reference must diagonalize the actual stored float32 tensor, not
    # its pre-narrowing construction, especially near the validity boundary.
    matrices = matrices.astype(np.float32).astype(np.float64)
    reference = np.linalg.eigvalsh(matrices)
    radius = np.max(np.abs(reference), axis=1)
    tolerance = 32 * np.finfo(np.float32).eps * radius
    expected = reference[:, 0] >= -tolerance
    raw = matrices[:, [0, 0, 0, 1, 1, 2], [0, 1, 2, 1, 2, 2]]
    request = "".join(" ".join(map(repr, row.tolist())) + "\n" for row in raw)

    with tempfile.TemporaryDirectory(prefix="dtcc-qes-stress-validity-") as directory:
        source, binary = Path(directory) / "probe.cpp", Path(directory) / "probe"
        source.write_text(PROBE)
        subprocess.run([args.compiler, "-std=c++17", "-O2", "-I", str(ROOT / "src/qes_core/dtcc/api"),
                        str(source), "-o", str(binary)], check=True)
        result = subprocess.run([str(binary)], input=request, text=True,
                                capture_output=True, check=True)
    actual = np.fromstring(result.stdout, sep=" ").reshape(count, 4)
    np.testing.assert_array_equal(actual[:, 0].astype(bool), expected)
    error = np.abs(actual[:, 1] - reference[:, 0]) / radius
    if error.max() >= 5e-13:
        raise RuntimeError(f"Minimum-eigenvalue error exceeds tolerance: {error.max()}")
    np.testing.assert_allclose(actual[:, 2], radius, rtol=5e-13, atol=0)
    np.testing.assert_allclose(actual[:, 3], tolerance, rtol=5e-13, atol=0)
    print(json.dumps(dict(seed=args.seed, cases=count, numpy=np.__version__,
        compiler=args.compiler, header_sha256=hashlib.sha256(
            (ROOT / "src/qes_core/dtcc/api/stress_validity.h").read_bytes()).hexdigest(),
        validity_mismatches=int(np.count_nonzero(actual[:, 0].astype(bool) != expected)),
        maximum_eigenvalue_error_over_spectral_radius=float(error.max()),
        scale_range=[1e-30, 1e30]), indent=2))


if __name__ == "__main__":
    main()

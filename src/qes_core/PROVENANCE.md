# Vendored QES-Winds core

This directory holds the QES-Winds sources that dtcc-qes compiles. It is a
GPL-3.0 derivative of [QES-Public](https://github.com/UtahEFD/QES-Public)
(University of Utah and University of Minnesota Duluth); see `LICENSE` and the
source headers. Changes made here are ordinary dtcc-qes commits.

## Origin

| | Revision |
| --- | --- |
| Vendored from | `dwastberg/QES-Public`, branch `dtcc-embed`, commit `dce15d7e3b0a2d2cb0a29898f3882d103f66de71` |
| Upstream base | `UtahEFD/QES-Public` v2.3.1, commit `dced7ec571487be7538eca17bfc25bb3262fb6d0` |

The fork commits between the upstream base and the vendored revision are:

1. `47645fa0` Separate the I/O-free QES core and support embedding builds
2. `74817ae4` Introduce silent leveled diagnostics and throwing QES errors
3. `d530b4a3` Own internal wind objects and validate borrowed in-memory inputs
4. `f34034b7` Return solver diagnostics and handle exceptions in standalone drivers
5. `398e9a4e` Measure serial convergence before accepting permissive tolerances
6. `71f8dcb2` Make OpenMP convergence and solid-face updates safe and deterministic
7. `046eb799` Fix vertical divergence scaling in wind solver RHS
8. `e0fb62e9` Support validated explicit vertical grids in embedded winds
9. `514d91cd` Own turbulence helpers and guard reference sampling
10. `2df34fc8` Correct stress rotation and diagnose missing wind directions
11. `57ffb0d9` Fix serial mixing distances with bounded voxel-face updates
12. `dce15d7e` Honor explicit vertical layers in the standalone wind driver

`src/dtcc_qes/_qes_revision.txt` records the vendored revision. It is compiled
into the extension as `_qes.qes_revision`.

## Contents

`qes/`, `util/` and `winds/` contain exactly the files that the former
`QES-Public` subproject compiled with `QES_ENABLE_IO`, CUDA and OptiX off: the
`qesutil` and `qeswindscore` sources and every header they include. The list
was taken from compiler dependency files. The files are byte-identical to
`src/<path>` at the vendored revision. `LICENSE` is the QES license.
`CMakeLists.txt` is new: it reproduces the former `qesbuild`, `qesutil` and
`qeswindscore` targets with the same source order and compile settings.

Sources still contain `#if QES_ENABLE_IO`, `#ifdef HAS_CUDA` and `#ifdef HAS_OPTIX`
branches that include headers that were not vendored (I/O readers, GPU solvers,
OptiX). These branches are never compiled here. Plume, Fire, the standalone
executables and the I/O, WRF/HRRR, CUDA and OptiX sources were not vendored.

## Equivalence with the submodule build

At vendoring time, builds from the submodule and from this directory were
compared with AppleClang 17 in Release mode: OpenMP and serial, with and without
native tests. The normalized compile commands matched. Every object file, the
`_qes` extension module and every native test executable were byte-identical.
The static archives differed only in member timestamps. A 14-case Python API
matrix gave bitwise-identical velocity, turbulence, coordinate and diagnostic
outputs. The cases covered float32 and float64, explicit and automatic vertical
grids, both mixing-length methods, oblique winds and nonconverged runs.

To check that a file is still unmodified relative to the fork, compare it with
the submodule (reference-only, see the main README):

```sh
git -C QES-Public show dce15d7e:src/winds/Solver_CPU.cpp | diff - src/qes_core/winds/Solver_CPU.cpp
```

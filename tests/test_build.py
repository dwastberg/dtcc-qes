"""Checks for the private extension and the staged native symbol audit."""

import importlib.util
from importlib.resources import files
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("native_symbols", ROOT / "tools/check_native_symbols.py")
symbols = importlib.util.module_from_spec(spec)
spec.loader.exec_module(symbols)


def test_extension_links_core():
    from dtcc_qes import _qes

    assert _qes.io_enabled is False
    assert _qes.compiler_id and _qes.compiler_version and _qes.build_type
    assert _qes.qes_version == "v2.3.1"
    assert len(_qes.qes_revision) == 40
    assert _qes.qes_revision == files("dtcc_qes").joinpath("_qes_revision.txt").read_text().strip()
    assert _qes._core_grid_shape(4, 3, 2) == [4, 3, 2]
    with pytest.raises(ValueError):
        _qes._core_grid_shape(0, 3, 2)


@pytest.mark.parametrize(("symbol", "category"), [
    ("_exit", "termination"), ("__exit", "termination"),
    ("___assert_rtn", "termination"), ("__assert_fail", "termination"),
    ("_fopen", "file_io"), ("open@@GLIBC_2.2.5", "file_io"),
    ("std::__1::basic_ifstream<char>::open(char const*)", "file_io"),
    ("std::__cxx11::basic_filebuf<char>::close()", "file_io"),
    ("std::__1::filesystem::exists()", "file_io"),
    ("_nc_open", "io_libraries"), ("GDALOpen", "io_libraries"),
    ("netCDF::NcFile::NcFile()", "io_libraries"),
    ("boost::program_options::options_description()", "io_libraries"),
    ("std::__1::cout", "console"), ("___stderrp", "console"),
    ("__fprintf_chk", "console"),
])
def test_symbol_categories(symbol, category):
    assert category in symbols.categories_for(symbol)


@pytest.mark.parametrize("symbol", [
    "std::terminate()", "std::__1::basic_ostringstream<char>::str()",
    "operator new(unsigned long)", "_memcpy", "___cxa_throw",
])
def test_permitted_symbols(symbol):
    assert not symbols.categories_for(symbol)

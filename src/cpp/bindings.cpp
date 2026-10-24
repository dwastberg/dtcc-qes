#include <nanobind/nanobind.h>
#include <nanobind/stl/array.h>
#include "build_info.h"

NB_MODULE(_qes, m)
{
#ifdef DTCC_QES_DISTRIBUTABLE_BUILD
  nanobind::set_leak_warnings(false);
#endif
  m.doc() = "Private QES core build checks; wind runner not yet implemented";
  m.attr("qes_version") = dtcc_qes::qes_version();
  m.attr("qes_revision") = dtcc_qes::qes_revision();
  m.attr("io_enabled") = false;
  m.def("_core_grid_shape", &dtcc_qes::core_grid_shape);
}

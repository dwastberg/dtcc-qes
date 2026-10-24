#include "qes/Domain.h"
#include "winds/WINDSGeneralData.h"
#include "util/UnsupportedFeature.h"
#include <functional>
#include <stdexcept>

static void rejects(const std::function<void()> &operation)
{
  try {
    operation();
  } catch (const qes::UnsupportedFeature &) {
    return;
  }
  throw std::runtime_error("I/O-dependent configuration was accepted");
}

int main()
{
  qes::Domain domain(4, 3, 2, 2.0f, 2.0f, 2.0f);
  if (domain.getBaseDomainCellNum() != std::make_tuple(4, 3, 2))
    return 1;
  rejects([] { qes::Domain input("missing.nc"); });
  rejects([] { WINDSInputData input("missing.xml"); });
  rejects([] { Sensor sensor("missing.xml"); });
  rejects([] { WINDSGeneralData input("missing.nc"); });

  SimulationParameters simulation;
  MetParams met;
  BuildingsParams buildings;
  VegetationParams vegetation;
  WINDSInputData input;
  input.simParams = &simulation;
  input.metParams = &met;
  input.buildingsParams = &buildings;
  input.vegetationParams = &vegetation;
  rejects([&] { simulation.parseValues(); });
  rejects([&] { buildings.parseValues(); });
  rejects([&] { vegetation.parseValues(); });
  rejects([&] { met.parseValues(); });
  auto reject_input = [&] { WINDSGeneralData data(&input, domain, 1); };
  simulation.DTE_mesh = nullptr;
  simulation.demFile = "missing.tif";
  rejects(reject_input);
  simulation.demFile.clear();
  simulation.wrfFile = "missing.nc";
  rejects(reject_input);
  simulation.wrfFile.clear();
  simulation.readCoefficientsFlag = 1;
  rejects(reject_input);
  simulation.readCoefficientsFlag = 0;
  buildings.shpFile = "missing.shp";
  rejects(reject_input);
  buildings.shpFile.clear();
  met.sensorName.push_back("missing.xml");
  rejects(reject_input);
  met.sensorName.clear();
  HRRRInput hrrr;
  input.hrrrInput = &hrrr;
  rejects(reject_input);
  return 0;
}

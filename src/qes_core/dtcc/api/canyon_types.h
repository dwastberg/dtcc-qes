#pragma once
#include <stdexcept>
#include <string>
namespace dtcc_qes {
enum class CanyonModel { Legacy, HorizontalReferenceV1, JoinedV1 };
inline const char* canyon_model_name(CanyonModel model) {
  switch(model) {
    case CanyonModel::Legacy: return "legacy";
    case CanyonModel::HorizontalReferenceV1: return "horizontal_reference_v1";
    case CanyonModel::JoinedV1: return "joined_v1";
  }
  throw std::invalid_argument("Unknown research canyon model");
}
inline CanyonModel canyon_model_parse(const std::string& name) {
  if(name=="legacy") return CanyonModel::Legacy;
  if(name=="horizontal_reference_v1") return CanyonModel::HorizontalReferenceV1;
  if(name=="joined_v1") return CanyonModel::JoinedV1;
  throw std::invalid_argument("Unknown research canyon model: "+name);
}
inline constexpr const char* canyon_schema="qes-canyon-validation-v1";
inline constexpr const char* canyon_roof_protection_revision="physical-and-voxel-union-v1";
inline constexpr const char* canyon_join_spec_sha256="69ebbd560b8a562cabdde1451d8a456e3e3d96e503c3e32a97708a462d2fe689";
}

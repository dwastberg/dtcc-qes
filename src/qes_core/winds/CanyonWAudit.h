// Bitwise W preservation over the complete native face field, including ghosts.
#include <cstring>
void joint_horizontal_W_audit(WINDSGeneralData *data,const std::vector<float>& before)
{
  if (before.size()!=data->w0.size()) throw std::runtime_error("W audit shape changed");
  for (std::size_t f=0;f<before.size();++f)
    if (std::memcmp(&before[f],&data->w0[f],sizeof(float))) ++data->canyon_W_changes;
}

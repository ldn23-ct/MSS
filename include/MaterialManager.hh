#ifndef MATERIAL_MANAGER_HH
#define MATERIAL_MANAGER_HH

#include <string>

class G4Material;

class MaterialManager {
  public:
    MaterialManager() = default;

    G4Material* GetMaterial(const std::string& name) const;
};

#endif

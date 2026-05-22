#ifndef REGION_REGISTRY_HH
#define REGION_REGISTRY_HH

#include <optional>
#include <string>
#include <unordered_map>

class G4VPhysicalVolume;

class RegionRegistry {
  public:
    RegionRegistry() = default;

    void Register(const G4VPhysicalVolume* volume, const std::string& regionId);
    std::optional<std::string> FindRegionId(const G4VPhysicalVolume* volume) const;
    bool Contains(const G4VPhysicalVolume* volume) const;
    void Clear();

  private:
    std::unordered_map<const G4VPhysicalVolume*, std::string> regions_;
};

#endif

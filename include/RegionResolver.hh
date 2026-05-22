#ifndef REGION_RESOLVER_HH
#define REGION_RESOLVER_HH

#include <string>

class G4VPhysicalVolume;
class RegionRegistry;

class RegionResolver {
  public:
    RegionResolver() = default;
    explicit RegionResolver(const RegionRegistry* registry);
    explicit RegionResolver(const RegionRegistry& registry);

    void SetRegistry(const RegionRegistry* registry);
    void SetVehicleROIVolume(const G4VPhysicalVolume* volume);

    std::string Resolve(const G4VPhysicalVolume* preStepVolume) const;
    std::string ResolvePreStepVolume(const G4VPhysicalVolume* preStepVolume) const;

  private:
    const RegionRegistry* registry_ = nullptr;
    const G4VPhysicalVolume* vehicleROIVolume_ = nullptr;
};

#endif

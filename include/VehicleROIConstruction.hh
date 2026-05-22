#ifndef VEHICLE_ROI_CONSTRUCTION_HH
#define VEHICLE_ROI_CONSTRUCTION_HH

#include "SimulationConfig.hh"
#include "VehicleROIConfig.hh"

#include <map>
#include <string>

class G4LogicalVolume;
class G4VPhysicalVolume;
class MaterialManager;
class RegionRegistry;

class VehicleROIConstruction {
  public:
    VehicleROIConstruction(
        const VehicleROIConfig& vehicleROI,
        const VehicleRunConfig& vehicleRun,
        const MaterialManager& materialManager,
        RegionRegistry& regionRegistry);

    G4VPhysicalVolume* Construct(G4LogicalVolume* worldLogical);
    G4VPhysicalVolume* RootPhysicalVolume() const;

  private:
    std::string ResolveMaterialName(const BoxComponentConfig& component) const;
    std::string ResolveRegionId(const BoxComponentConfig& component) const;
    void ApplyVisualAttributes(
        G4LogicalVolume* logical,
        const std::string& materialName,
        const std::string& regionId) const;

    const VehicleROIConfig& vehicleROI_;
    const VehicleRunConfig& vehicleRun_;
    const MaterialManager& materialManager_;
    RegionRegistry& regionRegistry_;
    std::map<std::string, G4LogicalVolume*> logicalVolumes_;
    std::map<std::string, G4VPhysicalVolume*> physicalVolumes_;
    G4VPhysicalVolume* rootPhysicalVolume_ = nullptr;
};

#endif

#ifndef DETECTOR_CONSTRUCTION_HH
#define DETECTOR_CONSTRUCTION_HH

#include "MaterialManager.hh"
#include "RegionRegistry.hh"
#include "RegionResolver.hh"
#include "SimulationConfig.hh"
#include "VehicleROIConfig.hh"

#include "G4VUserDetectorConstruction.hh"

class G4VPhysicalVolume;

class DetectorConstruction : public G4VUserDetectorConstruction {
  public:
    DetectorConstruction() = default;
    DetectorConstruction(SimulationConfig simulationConfig, VehicleROIConfig vehicleROIConfig);
    ~DetectorConstruction() override = default;

    G4VPhysicalVolume* Construct() override;

    const RegionRegistry& GetRegionRegistry() const;
    const RegionResolver& GetRegionResolver() const;
    G4VPhysicalVolume* WorldPhysicalVolume() const;
    G4VPhysicalVolume* VehicleROIPhysicalVolume() const;

  private:
    void RequireConfigured() const;
    void ValidateWorldContainsVehicleROI() const;

    bool configured_ = false;
    SimulationConfig simulationConfig_;
    VehicleROIConfig vehicleROIConfig_;
    MaterialManager materialManager_;
    RegionRegistry regionRegistry_;
    RegionResolver regionResolver_{regionRegistry_};
    G4VPhysicalVolume* worldPhysicalVolume_ = nullptr;
    G4VPhysicalVolume* vehicleROIPhysicalVolume_ = nullptr;
};

#endif

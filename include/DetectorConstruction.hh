#ifndef DETECTOR_CONSTRUCTION_HH
#define DETECTOR_CONSTRUCTION_HH

#include "G4VUserDetectorConstruction.hh"

#include <memory>

class G4VPhysicalVolume;
struct SimulationConfig;

class DetectorConstruction : public G4VUserDetectorConstruction {
  public:
    explicit DetectorConstruction(std::shared_ptr<const SimulationConfig> config);
    ~DetectorConstruction() override = default;

    G4VPhysicalVolume* Construct() override;

  private:
    std::shared_ptr<const SimulationConfig> config_;
};

#endif

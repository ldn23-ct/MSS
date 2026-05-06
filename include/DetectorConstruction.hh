#ifndef DETECTOR_CONSTRUCTION_HH
#define DETECTOR_CONSTRUCTION_HH

#include "G4VUserDetectorConstruction.hh"

#include <memory>

class G4VPhysicalVolume;
struct SimulationConfig;

struct DetectorPlaneConfig {
    double z_mm = -73.0;
    double x_min_mm = 53.0;
    double x_max_mm = 161.0;
    double y_min_mm = -50.0;
    double y_max_mm = 50.0;
};

class DetectorConstruction : public G4VUserDetectorConstruction {
  public:
    explicit DetectorConstruction(std::shared_ptr<const SimulationConfig> config);
    ~DetectorConstruction() override = default;

    G4VPhysicalVolume* Construct() override;
    const DetectorPlaneConfig& GetDetectorPlaneConfig() const;

  private:
    std::shared_ptr<const SimulationConfig> config_;
    DetectorPlaneConfig detectorPlaneConfig_;
};

#endif

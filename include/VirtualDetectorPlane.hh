#ifndef VIRTUAL_DETECTOR_PLANE_HH
#define VIRTUAL_DETECTOR_PLANE_HH

#include "ScanPoseManager.hh"
#include "SimulationConfig.hh"

class G4LogicalVolume;
class G4VPhysicalVolume;
class MaterialManager;

struct DetectorPlaneActual {
    double z_mm = 0.0;
    double x_min_mm = 0.0;
    double x_max_mm = 0.0;
    double y_min_mm = 0.0;
    double y_max_mm = 0.0;
};

class VirtualDetectorPlane {
  public:
    static constexpr double kHelperThicknessMm = 0.1;

    VirtualDetectorPlane() = default;
    VirtualDetectorPlane(const DetectorConfig& detectorConfig, const ScanPose& pose);

    static DetectorPlaneActual CalculateActual(const DetectorConfig& detectorConfig, const ScanPose& pose);

    const DetectorPlaneActual& Actual() const;
    G4VPhysicalVolume* Construct(G4LogicalVolume* motherLogical, const MaterialManager& materialManager);
    G4VPhysicalVolume* PhysicalVolume() const;

  private:
    DetectorConfig detectorConfig_;
    ScanPose pose_;
    DetectorPlaneActual actual_;
    G4VPhysicalVolume* physicalVolume_ = nullptr;
};

#endif

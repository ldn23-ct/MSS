#ifndef IMAGING_HEAD_CONSTRUCTION_HH
#define IMAGING_HEAD_CONSTRUCTION_HH

#include "ScanPoseManager.hh"
#include "SimulationConfig.hh"
#include "VirtualDetectorPlane.hh"

#include <array>

class G4LogicalVolume;
class G4VPhysicalVolume;
class MaterialManager;

class ImagingHeadConstruction {
  public:
    ImagingHeadConstruction() = default;
    ImagingHeadConstruction(
        const SimulationConfig& simulationConfig,
        const ScanPose& pose,
        const MaterialManager& materialManager);

    G4VPhysicalVolume* Construct(G4LogicalVolume* worldLogical);

    const std::array<double, 3>& SourcePositionActualMm() const;
    const VirtualDetectorPlane& DetectorPlane() const;
    G4VPhysicalVolume* VirtualDetectorPhysicalVolume() const;

  private:
    void RequireConfigured() const;

    const SimulationConfig* simulationConfig_ = nullptr;
    ScanPose pose_;
    const MaterialManager* materialManager_ = nullptr;
    std::array<double, 3> sourcePositionActualMm_ = {0.0, 0.0, 0.0};
    VirtualDetectorPlane detectorPlane_;
    G4VPhysicalVolume* virtualDetectorPhysicalVolume_ = nullptr;
};

#endif

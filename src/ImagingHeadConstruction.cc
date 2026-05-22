#include "ImagingHeadConstruction.hh"

#include <stdexcept>

namespace {

std::array<double, 3> CalculateSourceActual(const SourceConfig& sourceConfig, const ScanPose& pose)
{
    return {
        sourceConfig.source_pos_zero_mm[0] + pose.head_offset_x_mm,
        sourceConfig.source_pos_zero_mm[1] + pose.head_offset_y_mm,
        sourceConfig.source_pos_zero_mm[2]};
}

}  // namespace

ImagingHeadConstruction::ImagingHeadConstruction(
    const SimulationConfig& simulationConfig,
    const ScanPose& pose,
    const MaterialManager& materialManager)
    : simulationConfig_(&simulationConfig),
      pose_(pose),
      materialManager_(&materialManager),
      sourcePositionActualMm_(CalculateSourceActual(simulationConfig.source, pose)),
      detectorPlane_(simulationConfig.detector, pose)
{
}

G4VPhysicalVolume* ImagingHeadConstruction::Construct(G4LogicalVolume* worldLogical)
{
    RequireConfigured();
    virtualDetectorPhysicalVolume_ = detectorPlane_.Construct(worldLogical, *materialManager_);
    return virtualDetectorPhysicalVolume_;
}

const std::array<double, 3>& ImagingHeadConstruction::SourcePositionActualMm() const
{
    RequireConfigured();
    return sourcePositionActualMm_;
}

const VirtualDetectorPlane& ImagingHeadConstruction::DetectorPlane() const
{
    RequireConfigured();
    return detectorPlane_;
}

G4VPhysicalVolume* ImagingHeadConstruction::VirtualDetectorPhysicalVolume() const
{
    return virtualDetectorPhysicalVolume_;
}

void ImagingHeadConstruction::RequireConfigured() const
{
    if (simulationConfig_ == nullptr || materialManager_ == nullptr) {
        throw std::runtime_error("ImagingHeadConstruction requires SimulationConfig, ScanPose, and MaterialManager");
    }
}

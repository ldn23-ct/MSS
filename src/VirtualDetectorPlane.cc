#include "VirtualDetectorPlane.hh"

#include "MaterialManager.hh"

#include "G4Box.hh"
#include "G4Colour.hh"
#include "G4LogicalVolume.hh"
#include "G4PVPlacement.hh"
#include "G4SystemOfUnits.hh"
#include "G4VisAttributes.hh"

#include <stdexcept>

namespace {

DetectorPlaneActual CalculateActual(const DetectorConfig& detectorConfig, const ScanPose& pose)
{
    DetectorPlaneActual actual;
    actual.z_mm = detectorConfig.detector_z_zero_mm;
    actual.x_min_mm = detectorConfig.detector_x_range_zero_mm[0] + pose.head_offset_x_mm;
    actual.x_max_mm = detectorConfig.detector_x_range_zero_mm[1] + pose.head_offset_x_mm;
    actual.y_min_mm = detectorConfig.detector_y_range_zero_mm[0] + pose.head_offset_y_mm;
    actual.y_max_mm = detectorConfig.detector_y_range_zero_mm[1] + pose.head_offset_y_mm;
    return actual;
}

}  // namespace

VirtualDetectorPlane::VirtualDetectorPlane(const DetectorConfig& detectorConfig, const ScanPose& pose)
    : detectorConfig_(detectorConfig),
      pose_(pose),
      actual_(CalculateActual(detectorConfig, pose))
{
}

const DetectorPlaneActual& VirtualDetectorPlane::Actual() const
{
    return actual_;
}

G4VPhysicalVolume* VirtualDetectorPlane::Construct(
    G4LogicalVolume* motherLogical,
    const MaterialManager& materialManager)
{
    if (motherLogical == nullptr) {
        throw std::runtime_error("VirtualDetectorPlane requires a non-null mother logical volume");
    }
    if (actual_.x_min_mm >= actual_.x_max_mm || actual_.y_min_mm >= actual_.y_max_mm) {
        throw std::runtime_error("VirtualDetectorPlane actual bounds are invalid");
    }

    const double centerX = 0.5 * (actual_.x_min_mm + actual_.x_max_mm);
    const double centerY = 0.5 * (actual_.y_min_mm + actual_.y_max_mm);
    const double halfX = 0.5 * (actual_.x_max_mm - actual_.x_min_mm);
    const double halfY = 0.5 * (actual_.y_max_mm - actual_.y_min_mm);
    const double halfZ = 0.5 * kHelperThicknessMm;

    auto* material = materialManager.GetMaterial("G4_AIR");
    auto* solid = new G4Box(
        "VirtualDetectorPlaneSolid_" + pose_.pose_id,
        halfX * mm,
        halfY * mm,
        halfZ * mm);
    auto* logical = new G4LogicalVolume(
        solid,
        material,
        "VirtualDetectorPlaneLogical_" + pose_.pose_id);

    auto* attributes = new G4VisAttributes(G4Colour(0.1, 0.8, 1.0, 0.35));
    attributes->SetVisibility(true);
    attributes->SetForceSolid(true);
    logical->SetVisAttributes(attributes);

    physicalVolume_ = new G4PVPlacement(
        nullptr,
        G4ThreeVector(centerX * mm, centerY * mm, actual_.z_mm * mm),
        logical,
        "VirtualDetectorPlanePhysical_" + pose_.pose_id,
        motherLogical,
        false,
        pose_.pose_index,
        true);

    return physicalVolume_;
}

G4VPhysicalVolume* VirtualDetectorPlane::PhysicalVolume() const
{
    return physicalVolume_;
}

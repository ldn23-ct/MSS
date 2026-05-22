#include "DetectorConstruction.hh"

#include "ImagingHeadConstruction.hh"
#include "VehicleROIConstruction.hh"
#include "VirtualDetectorPlane.hh"

#include "G4Box.hh"
#include "G4LogicalVolume.hh"
#include "G4PVPlacement.hh"
#include "G4SystemOfUnits.hh"
#include "G4VisAttributes.hh"

#include <stdexcept>
#include <utility>

namespace {

bool AxisContains(double worldCenter, double worldSize, const std::array<double, 2>& child)
{
    const double half = worldSize * 0.5;
    return child[0] >= worldCenter - half && child[1] <= worldCenter + half;
}

bool AxisContainsValue(double worldCenter, double worldSize, double value)
{
    const double half = worldSize * 0.5;
    return value >= worldCenter - half && value <= worldCenter + half;
}

std::array<double, 2> DetectorZExtent(const DetectorPlaneActual& actual)
{
    const double halfThickness = 0.5 * VirtualDetectorPlane::kHelperThicknessMm;
    return {actual.z_mm - halfThickness, actual.z_mm + halfThickness};
}

}  // namespace

DetectorConstruction::DetectorConstruction(SimulationConfig simulationConfig, VehicleROIConfig vehicleROIConfig)
    : configured_(true),
      simulationConfig_(std::move(simulationConfig)),
      vehicleROIConfig_(std::move(vehicleROIConfig))
{
}

G4VPhysicalVolume* DetectorConstruction::Construct()
{
    RequireConfigured();
    ScanPoseManager poseManager;
    const PoseList poses = poseManager.Generate(simulationConfig_);
    ValidateWorldContainsVehicleROI();
    ValidateWorldContainsImagingHeadPoses(poses);

    regionRegistry_.Clear();
    worldPhysicalVolume_ = nullptr;
    vehicleROIPhysicalVolume_ = nullptr;
    virtualDetectorPhysicalVolume_ = nullptr;

    auto* worldMaterial = materialManager_.GetMaterial(simulationConfig_.world.material);
    auto* worldSolid = new G4Box(
        "WorldSolid",
        simulationConfig_.world.size_mm[0] * 0.5 * mm,
        simulationConfig_.world.size_mm[1] * 0.5 * mm,
        simulationConfig_.world.size_mm[2] * 0.5 * mm);
    auto* worldLogical = new G4LogicalVolume(worldSolid, worldMaterial, "WorldLogical");
    worldLogical->SetVisAttributes(G4VisAttributes::GetInvisible());

    worldPhysicalVolume_ = new G4PVPlacement(
        nullptr,
        G4ThreeVector(
            simulationConfig_.world.center_mm[0] * mm,
            simulationConfig_.world.center_mm[1] * mm,
            simulationConfig_.world.center_mm[2] * mm),
        worldLogical,
        "WorldPhysical",
        nullptr,
        false,
        0,
        true);

    VehicleROIConstruction vehicleConstruction(
        vehicleROIConfig_, simulationConfig_.vehicle, materialManager_, regionRegistry_);
    vehicleROIPhysicalVolume_ = vehicleConstruction.Construct(worldLogical);
    regionResolver_.SetVehicleROIVolume(vehicleROIPhysicalVolume_);

    ImagingHeadConstruction imagingHead(simulationConfig_, poses.front(), materialManager_);
    virtualDetectorPhysicalVolume_ = imagingHead.Construct(worldLogical);

    return worldPhysicalVolume_;
}

const RegionRegistry& DetectorConstruction::GetRegionRegistry() const
{
    return regionRegistry_;
}

const RegionResolver& DetectorConstruction::GetRegionResolver() const
{
    return regionResolver_;
}

G4VPhysicalVolume* DetectorConstruction::WorldPhysicalVolume() const
{
    return worldPhysicalVolume_;
}

G4VPhysicalVolume* DetectorConstruction::VehicleROIPhysicalVolume() const
{
    return vehicleROIPhysicalVolume_;
}

G4VPhysicalVolume* DetectorConstruction::VirtualDetectorPhysicalVolume() const
{
    return virtualDetectorPhysicalVolume_;
}

void DetectorConstruction::RequireConfigured() const
{
    if (!configured_) {
        throw std::runtime_error("DetectorConstruction requires SimulationConfig and VehicleROIConfig for M4 geometry");
    }
}

void DetectorConstruction::ValidateWorldContainsVehicleROI() const
{
    const auto& world = simulationConfig_.world;
    const auto& roi = vehicleROIConfig_.root_roi.aabb_mm;
    if (!AxisContains(world.center_mm[0], world.size_mm[0], roi.x)
        || !AxisContains(world.center_mm[1], world.size_mm[1], roi.y)
        || !AxisContains(world.center_mm[2], world.size_mm[2], roi.z)) {
        throw std::runtime_error("VehicleROI is outside fixed World bounds");
    }
}

void DetectorConstruction::ValidateWorldContainsImagingHeadPoses(const PoseList& poses) const
{
    if (poses.empty()) {
        throw std::runtime_error("at least one ScanPose is required to construct ImagingHead");
    }

    const auto& world = simulationConfig_.world;
    for (const auto& pose : poses) {
        const std::array<double, 3> sourceActual = {
            simulationConfig_.source.source_pos_zero_mm[0] + pose.head_offset_x_mm,
            simulationConfig_.source.source_pos_zero_mm[1] + pose.head_offset_y_mm,
            simulationConfig_.source.source_pos_zero_mm[2]};

        if (!AxisContainsValue(world.center_mm[0], world.size_mm[0], sourceActual[0])
            || !AxisContainsValue(world.center_mm[1], world.size_mm[1], sourceActual[1])
            || !AxisContainsValue(world.center_mm[2], world.size_mm[2], sourceActual[2])) {
            throw std::runtime_error("source position is outside fixed World bounds for pose " + pose.pose_id);
        }

        const VirtualDetectorPlane detectorPlane(simulationConfig_.detector, pose);
        const auto& actual = detectorPlane.Actual();
        const std::array<double, 2> zExtent = DetectorZExtent(actual);
        if (!AxisContains(world.center_mm[0], world.size_mm[0], {actual.x_min_mm, actual.x_max_mm})
            || !AxisContains(world.center_mm[1], world.size_mm[1], {actual.y_min_mm, actual.y_max_mm})
            || !AxisContains(world.center_mm[2], world.size_mm[2], zExtent)) {
            throw std::runtime_error("virtual detector plane is outside fixed World bounds for pose " + pose.pose_id);
        }
    }
}

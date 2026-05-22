#include "DetectorConstruction.hh"

#include "VehicleROIConstruction.hh"

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
    ValidateWorldContainsVehicleROI();

    regionRegistry_.Clear();
    worldPhysicalVolume_ = nullptr;
    vehicleROIPhysicalVolume_ = nullptr;

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

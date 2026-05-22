#include "VehicleROIConstruction.hh"

#include "MaterialManager.hh"
#include "RegionRegistry.hh"

#include "G4Box.hh"
#include "G4Colour.hh"
#include "G4LogicalVolume.hh"
#include "G4PVPlacement.hh"
#include "G4SystemOfUnits.hh"
#include "G4VisAttributes.hh"

#include <stdexcept>

namespace {

G4ThreeVector ToG4Vector(const std::array<double, 3>& value)
{
    return G4ThreeVector(value[0] * mm, value[1] * mm, value[2] * mm);
}

G4Colour ColourForMaterial(const std::string& materialName, const std::string& regionId)
{
    if (regionId == "target") {
        return G4Colour(1.0, 0.1, 0.1, 0.85);
    }
    if (materialName == "G4_AIR") {
        return G4Colour(0.7, 0.9, 1.0, 0.12);
    }
    if (materialName == "G4_Fe") {
        return G4Colour(0.55, 0.55, 0.60, 0.75);
    }
    if (materialName == "G4_GLASS_PLATE") {
        return G4Colour(0.2, 0.8, 0.95, 0.35);
    }
    if (materialName == "G4_POLYPROPYLENE") {
        return G4Colour(0.1, 0.55, 0.25, 0.55);
    }
    if (materialName == "Vehicle_PU_Foam") {
        return G4Colour(0.95, 0.72, 0.20, 0.55);
    }
    if (materialName == "G4_W") {
        return G4Colour(0.25, 0.25, 0.28, 0.9);
    }
    return G4Colour(0.8, 0.8, 0.8, 0.5);
}

}  // namespace

VehicleROIConstruction::VehicleROIConstruction(
    const VehicleROIConfig& vehicleROI,
    const VehicleRunConfig& vehicleRun,
    const MaterialManager& materialManager,
    RegionRegistry& regionRegistry)
    : vehicleROI_(vehicleROI),
      vehicleRun_(vehicleRun),
      materialManager_(materialManager),
      regionRegistry_(regionRegistry)
{
}

G4VPhysicalVolume* VehicleROIConstruction::Construct(G4LogicalVolume* worldLogical)
{
    if (worldLogical == nullptr) {
        throw std::runtime_error("VehicleROIConstruction requires a non-null World logical volume");
    }
    if (vehicleROI_.components.empty()) {
        throw std::runtime_error("VehicleROIConfig contains no components");
    }

    logicalVolumes_.clear();
    physicalVolumes_.clear();
    rootPhysicalVolume_ = nullptr;

    for (const auto& component : vehicleROI_.components) {
        if (component.shape != "box") {
            throw std::runtime_error(component.name + " uses unsupported shape: " + component.shape);
        }

        G4LogicalVolume* motherLogical = nullptr;
        if (component.host == "World") {
            motherLogical = worldLogical;
        } else {
            const auto hostIt = logicalVolumes_.find(component.host);
            if (hostIt == logicalVolumes_.end()) {
                throw std::runtime_error(component.name + " host logical volume has not been built: " + component.host);
            }
            motherLogical = hostIt->second;
        }

        const auto materialName = ResolveMaterialName(component);
        const auto regionId = ResolveRegionId(component);
        auto* material = materialManager_.GetMaterial(materialName);
        auto* solid = new G4Box(
            component.name + "Solid",
            component.half_size_mm[0] * mm,
            component.half_size_mm[1] * mm,
            component.half_size_mm[2] * mm);
        auto* logical = new G4LogicalVolume(solid, material, component.name + "Logical");
        ApplyVisualAttributes(logical, materialName, regionId);

        auto* physical = new G4PVPlacement(
            nullptr,
            ToG4Vector(component.placement_center_in_host_mm),
            logical,
            component.name + "Physical",
            motherLogical,
            false,
            0,
            true);

        logicalVolumes_.emplace(component.name, logical);
        physicalVolumes_.emplace(component.name, physical);
        regionRegistry_.Register(physical, regionId);

        if (component.name == vehicleROI_.root_roi.name) {
            rootPhysicalVolume_ = physical;
        }
    }

    if (rootPhysicalVolume_ == nullptr) {
        throw std::runtime_error("VehicleROI root physical volume was not constructed");
    }
    return rootPhysicalVolume_;
}

G4VPhysicalVolume* VehicleROIConstruction::RootPhysicalVolume() const
{
    return rootPhysicalVolume_;
}

std::string VehicleROIConstruction::ResolveMaterialName(const BoxComponentConfig& component) const
{
    if (!component.is_insert) {
        return component.material;
    }
    if (!component.normal_material) {
        throw std::runtime_error(component.name + " insert is missing normal material");
    }

    if (vehicleRun_.model_type == "normal") {
        return *component.normal_material;
    }
    if (vehicleRun_.model_type != "abnormal") {
        throw std::runtime_error("vehicle.model_type must be normal or abnormal");
    }
    if (!vehicleRun_.selected_target_component || vehicleRun_.selected_target_component->empty()) {
        throw std::runtime_error("abnormal model_type requires selected_target_component");
    }
    if (component.name == *vehicleRun_.selected_target_component) {
        return vehicleRun_.abnormal_material;
    }
    return *component.normal_material;
}

std::string VehicleROIConstruction::ResolveRegionId(const BoxComponentConfig& component) const
{
    if (!component.is_insert) {
        return component.region_id;
    }
    if (!component.normal_region_id) {
        throw std::runtime_error(component.name + " insert is missing normal region_id");
    }

    if (vehicleRun_.model_type == "normal") {
        return *component.normal_region_id;
    }
    if (vehicleRun_.model_type != "abnormal") {
        throw std::runtime_error("vehicle.model_type must be normal or abnormal");
    }
    if (!vehicleRun_.selected_target_component || vehicleRun_.selected_target_component->empty()) {
        throw std::runtime_error("abnormal model_type requires selected_target_component");
    }
    if (component.name == *vehicleRun_.selected_target_component) {
        return "target";
    }
    return *component.normal_region_id;
}

void VehicleROIConstruction::ApplyVisualAttributes(
    G4LogicalVolume* logical,
    const std::string& materialName,
    const std::string& regionId) const
{
    if (logical == nullptr) {
        return;
    }

    auto* attributes = new G4VisAttributes(ColourForMaterial(materialName, regionId));
    attributes->SetVisibility(true);
    attributes->SetForceSolid(false);
    logical->SetVisAttributes(attributes);
}

#include "MaterialManager.hh"

#include "G4Material.hh"
#include "G4NistManager.hh"
#include "G4SystemOfUnits.hh"

#include <stdexcept>
#include <string>

namespace {

G4Material* FindExistingMaterial(const std::string& name)
{
    return G4Material::GetMaterial(name, false);
}

G4Material* BuildVehiclePUFoam()
{
    if (auto* existing = FindExistingMaterial("Vehicle_PU_Foam")) {
        return existing;
    }

    auto* nist = G4NistManager::Instance();
    auto* foam = new G4Material("Vehicle_PU_Foam", 0.055 * g / cm3, 4);
    foam->AddElement(nist->FindOrBuildElement("C"), 0.60);
    foam->AddElement(nist->FindOrBuildElement("H"), 0.08);
    foam->AddElement(nist->FindOrBuildElement("O"), 0.28);
    foam->AddElement(nist->FindOrBuildElement("N"), 0.04);
    return foam;
}

G4Material* BuildVehicleFlour()
{
    if (auto* existing = FindExistingMaterial("Vehicle_Flour")) {
        return existing;
    }

    auto* nist = G4NistManager::Instance();
    auto* flour = new G4Material("Vehicle_Flour", 0.60 * g / cm3, 4);
    flour->AddElement(nist->FindOrBuildElement("C"), 0.44);
    flour->AddElement(nist->FindOrBuildElement("H"), 0.062);
    flour->AddElement(nist->FindOrBuildElement("O"), 0.493);
    flour->AddElement(nist->FindOrBuildElement("N"), 0.005);
    return flour;
}

}  // namespace

G4Material* MaterialManager::GetMaterial(const std::string& name) const
{
    if (name.empty()) {
        throw std::runtime_error("material name must be non-empty");
    }

    if (name == "Vehicle_PU_Foam") {
        return BuildVehiclePUFoam();
    }
    if (name == "Vehicle_Flour") {
        return BuildVehicleFlour();
    }

    if (auto* existing = FindExistingMaterial(name)) {
        return existing;
    }

    auto* material = G4NistManager::Instance()->FindOrBuildMaterial(name);
    if (material == nullptr) {
        throw std::runtime_error("failed to build NIST material: " + name);
    }
    return material;
}

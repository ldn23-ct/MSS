#include "MaterialManager.hh"

#include "G4Material.hh"
#include "G4NistManager.hh"
#include "G4SystemOfUnits.hh"

#include <stdexcept>
#include <string>

namespace {

bool IsSupportedNistMaterial(const std::string& name)
{
    return name == "G4_AIR"
        || name == "G4_Fe"
        || name == "G4_GLASS_PLATE"
        || name == "G4_POLYPROPYLENE"
        || name == "G4_POLYETHYLENE"
        || name == "G4_W";
}

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

}  // namespace

G4Material* MaterialManager::GetMaterial(const std::string& name) const
{
    if (name.empty()) {
        throw std::runtime_error("material name must be non-empty");
    }

    if (name == "Vehicle_PU_Foam") {
        return BuildVehiclePUFoam();
    }

    if (!IsSupportedNistMaterial(name)) {
        throw std::runtime_error("unsupported material: " + name);
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

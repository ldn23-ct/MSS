#include "CollimatorBuilder.hh"

#include "CollimatorProfileReader.hh"

#include "G4Colour.hh"
#include "G4ExtrudedSolid.hh"
#include "G4LogicalVolume.hh"
#include "G4Material.hh"
#include "G4PVPlacement.hh"
#include "G4RotationMatrix.hh"
#include "G4SystemOfUnits.hh"
#include "G4ThreeVector.hh"
#include "G4TwoVector.hh"
#include "G4VisAttributes.hh"

#include <array>
#include <string>
#include <vector>

namespace {

constexpr double kJawHalfLengthY = 60.0;

std::vector<G4TwoVector> BuildPolygon(
    const std::array<XZPoint, 5>& vertices)
{
    std::vector<G4TwoVector> polygon;
    polygon.reserve(vertices.size());

    for (const auto& vertex : vertices) {
        polygon.emplace_back(vertex.x_mm * mm, vertex.z_mm * mm);
    }

    return polygon;
}

void BuildJaw(const PentagonJawProfile& jaw,
              const std::string& index,
              G4LogicalVolume* parentLogical,
              G4Material* tungstenMaterial)
{
    const auto polygon = BuildPolygon(jaw.vertices);
    auto* solid = new G4ExtrudedSolid("CollimatorJaw" + index + "Solid",
                                      polygon,
                                      kJawHalfLengthY * mm,
                                      G4TwoVector(),
                                      1.0,
                                      G4TwoVector(),
                                      1.0);

    auto* logical = new G4LogicalVolume(solid,
                                        tungstenMaterial,
                                        "CollimatorJaw" + index + "Logical");

    auto* rotation = new G4RotationMatrix();
    rotation->rotateX(-90.0 * deg);

    new G4PVPlacement(rotation,
                      G4ThreeVector(),
                      logical,
                      "CollimatorJaw" + index + "Physical",
                      parentLogical,
                      false,
                      0,
                      true);

    auto* vis = new G4VisAttributes(G4Colour(0.45, 0.45, 0.45, 0.85));
    vis->SetForceSolid(true);
    logical->SetVisAttributes(vis);
}

} // namespace

void CollimatorBuilder::Build(const CollimatorProfile& profile,
                              G4LogicalVolume* parentLogical,
                              G4Material* tungstenMaterial) const
{
    BuildJaw(profile.jaw0, "0", parentLogical, tungstenMaterial);
    BuildJaw(profile.jaw1, "1", parentLogical, tungstenMaterial);
}

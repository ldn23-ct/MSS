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

#include <algorithm>
#include <cstddef>
#include <string>
#include <vector>

namespace {

constexpr double kJawHalfLengthY = 60.0;

double SignedArea(const std::vector<XZPoint>& vertices)
{
    double areaTwice = 0.0;
    for (std::size_t i = 0; i < vertices.size(); ++i) {
        const auto& current = vertices[i];
        const auto& next = vertices[(i + 1) % vertices.size()];
        areaTwice += current.x_mm * next.z_mm - next.x_mm * current.z_mm;
    }

    return 0.5 * areaTwice;
}

std::vector<XZPoint> BuildVertices(const PolygonJawProfile& jaw, bool mirrorX)
{
    std::vector<XZPoint> vertices;
    vertices.reserve(jaw.vertices.size());

    for (const auto& vertex : jaw.vertices) {
        vertices.push_back({mirrorX ? -vertex.x_mm : vertex.x_mm,
                            vertex.z_mm});
    }

    if (SignedArea(vertices) < 0.0) {
        std::reverse(vertices.begin(), vertices.end());
    }

    return vertices;
}

std::vector<G4TwoVector> BuildPolygon(const std::vector<XZPoint>& vertices)
{
    std::vector<G4TwoVector> polygon;
    polygon.reserve(vertices.size());

    for (const auto& vertex : vertices) {
        polygon.emplace_back(vertex.x_mm * mm, vertex.z_mm * mm);
    }

    return polygon;
}

void BuildJaw(const PolygonJawProfile& jaw,
              std::size_t index,
              bool mirrorX,
              G4LogicalVolume* parentLogical,
              G4Material* tungstenMaterial)
{
    const std::string suffix =
        std::to_string(index) + (mirrorX ? "Mirror" : "");
    const auto vertices = BuildVertices(jaw, mirrorX);
    const auto polygon = BuildPolygon(vertices);

    auto* solid = new G4ExtrudedSolid("CollimatorJaw" + suffix + "Solid",
                                      polygon,
                                      kJawHalfLengthY * mm,
                                      G4TwoVector(),
                                      1.0,
                                      G4TwoVector(),
                                      1.0);

    auto* logical = new G4LogicalVolume(solid,
                                        tungstenMaterial,
                                        "CollimatorJaw" + suffix + "Logical");

    auto* rotation = new G4RotationMatrix();
    rotation->rotateX(-90.0 * deg);

    new G4PVPlacement(rotation,
                      G4ThreeVector(),
                      logical,
                      "CollimatorJaw" + suffix + "Physical",
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
    for (std::size_t i = 0; i < profile.jaws.size(); ++i) {
        BuildJaw(profile.jaws[i], i, false, parentLogical, tungstenMaterial);
        BuildJaw(profile.jaws[i], i, true, parentLogical, tungstenMaterial);
    }
}

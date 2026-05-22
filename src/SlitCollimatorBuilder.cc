#include "SlitCollimatorBuilder.hh"

#include "MaterialManager.hh"

#include "G4Colour.hh"
#include "G4ExtrudedSolid.hh"
#include "G4LogicalVolume.hh"
#include "G4PVPlacement.hh"
#include "G4RotationMatrix.hh"
#include "G4SystemOfUnits.hh"
#include "G4TwoVector.hh"
#include "G4VisAttributes.hh"

#include <algorithm>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

struct XZBounds {
    double x_min = std::numeric_limits<double>::max();
    double x_max = std::numeric_limits<double>::lowest();
    double z_min = std::numeric_limits<double>::max();
    double z_max = std::numeric_limits<double>::lowest();
};

XZBounds CalculateActualBounds(const SlitJawProfile& jaw, const ScanPose& pose)
{
    if (jaw.vertices.empty()) {
        throw std::runtime_error(jaw.jaw_id + " has no vertices");
    }

    XZBounds bounds;
    for (const auto& vertex : jaw.vertices) {
        const double xActual = vertex.x_mm + pose.head_offset_x_mm;
        bounds.x_min = std::min(bounds.x_min, xActual);
        bounds.x_max = std::max(bounds.x_max, xActual);
        bounds.z_min = std::min(bounds.z_min, vertex.z_mm);
        bounds.z_max = std::max(bounds.z_max, vertex.z_mm);
    }
    return bounds;
}

std::string JawBaseName(const ScanPose& pose, const SlitJawProfile& jaw)
{
    return "SlitCollimatorJaw_" + pose.pose_id + "_" + jaw.jaw_id;
}

}  // namespace

std::vector<G4VPhysicalVolume*> SlitCollimatorBuilder::Build(
    const SlitCollimatorProfile& profile,
    const CollimatorConfig& collimatorConfig,
    const ScanPose& pose,
    G4LogicalVolume* motherLogical,
    const MaterialManager& materialManager) const
{
    if (motherLogical == nullptr) {
        throw std::runtime_error("SlitCollimatorBuilder requires a non-null mother logical volume");
    }
    if (profile.jaws.empty()) {
        throw std::runtime_error("SlitCollimatorProfile must contain at least one jaw");
    }
    if (collimatorConfig.jaw_extrusion_length_y_mm <= 0.0) {
        throw std::runtime_error("collimator.jaw_extrusion_length_y_mm must be > 0");
    }

    auto* tungstenMaterial = materialManager.GetMaterial("G4_W");
    auto rotation = std::make_unique<G4RotationMatrix>();
    rotation->rotateX(90.0 * deg);

    std::vector<G4VPhysicalVolume*> physicalVolumes;
    physicalVolumes.reserve(profile.jaws.size());

    for (std::size_t jawIndex = 0; jawIndex < profile.jaws.size(); ++jawIndex) {
        const auto& jaw = profile.jaws[jawIndex];
        const XZBounds bounds = CalculateActualBounds(jaw, pose);
        const double anchorX = 0.5 * (bounds.x_min + bounds.x_max);
        const double anchorZ = 0.5 * (bounds.z_min + bounds.z_max);
        const double centerY = jaw.y_zero_mm + pose.head_offset_y_mm;
        const double halfLengthY = 0.5 * collimatorConfig.jaw_extrusion_length_y_mm;

        std::vector<G4TwoVector> localVertices;
        localVertices.reserve(jaw.vertices.size());
        for (const auto& vertex : jaw.vertices) {
            const double xActual = vertex.x_mm + pose.head_offset_x_mm;
            const double zActual = vertex.z_mm;
            localVertices.emplace_back((xActual - anchorX) * mm, (zActual - anchorZ) * mm);
        }

        const std::string baseName = JawBaseName(pose, jaw);
        auto* solid = new G4ExtrudedSolid(
            baseName + "Solid",
            localVertices,
            halfLengthY * mm,
            G4TwoVector(0.0, 0.0),
            1.0,
            G4TwoVector(0.0, 0.0),
            1.0);
        auto* logical = new G4LogicalVolume(solid, tungstenMaterial, baseName + "Logical");

        auto* attributes = new G4VisAttributes(G4Colour(0.22, 0.22, 0.24, 0.92));
        attributes->SetVisibility(true);
        attributes->SetForceSolid(true);
        logical->SetVisAttributes(attributes);

        auto* physical = new G4PVPlacement(
            rotation.get(),
            G4ThreeVector(anchorX * mm, centerY * mm, anchorZ * mm),
            logical,
            baseName + "Physical",
            motherLogical,
            false,
            static_cast<int>(jawIndex),
            true);
        physicalVolumes.push_back(physical);
    }

    rotation.release();
    return physicalVolumes;
}

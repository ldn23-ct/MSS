#include "DetectorConstruction.hh"

#include "CollimatorBuilder.hh"
#include "CollimatorProfileReader.hh"
#include "SimulationConfig.hh"

#include "G4Box.hh"
#include "G4Colour.hh"
#include "G4LogicalVolume.hh"
#include "G4NistManager.hh"
#include "G4PVPlacement.hh"
#include "G4SystemOfUnits.hh"
#include "G4ThreeVector.hh"
#include "G4Tubs.hh"
#include "G4VisAttributes.hh"

#include <string>
#include <utility>

namespace {

constexpr double kWorldHalfLength = 500.0;

constexpr double kPmmaSizeX = 200.0;
constexpr double kPmmaSizeY = 200.0;
constexpr double kPmmaSizeZ = 65.0;
constexpr double kPmmaCenterZ = 32.5;

constexpr double kAirDefectRadius = 5.0;
constexpr double kAirDefectHalfLength = 5.0;
constexpr double kAirDefectCenterZ = 55.0;

constexpr double kDetectorPlaneThickness = 0.1;

void BuildDetectorPlaneVis(const DetectorPlaneConfig& config,
                           const std::string& suffix,
                           G4LogicalVolume* worldLogical,
                           G4Material* worldMaterial)
{
    const double detectorCenterX =
        0.5 * (config.x_min_mm + config.x_max_mm);
    const double detectorCenterY =
        0.5 * (config.y_min_mm + config.y_max_mm);
    const double detectorSizeX = config.x_max_mm - config.x_min_mm;
    const double detectorSizeY = config.y_max_mm - config.y_min_mm;

    auto* detectorPlaneSolid =
        new G4Box("DetectorPlaneVis" + suffix + "Solid",
                  0.5 * detectorSizeX * mm,
                  0.5 * detectorSizeY * mm,
                  0.5 * kDetectorPlaneThickness * mm);
    auto* detectorPlaneLogical =
        new G4LogicalVolume(detectorPlaneSolid,
                            worldMaterial,
                            "DetectorPlaneVis" + suffix + "Logical");

    new G4PVPlacement(nullptr,
                      G4ThreeVector(detectorCenterX * mm,
                                    detectorCenterY * mm,
                                    config.z_mm * mm),
                      detectorPlaneLogical,
                      "DetectorPlaneVis" + suffix + "Physical",
                      worldLogical,
                      false,
                      0,
                      true);

    auto* detectorVis = new G4VisAttributes(G4Colour(1.0, 0.1, 0.1, 0.45));
    detectorVis->SetForceSolid(true);
    detectorPlaneLogical->SetVisAttributes(detectorVis);
}

} // namespace

DetectorConstruction::DetectorConstruction(
    std::shared_ptr<const SimulationConfig> config)
    : config_(std::move(config))
{
}

G4VPhysicalVolume* DetectorConstruction::Construct()
{
    auto* nist = G4NistManager::Instance();
    auto* worldMaterial = nist->FindOrBuildMaterial("G4_Galactic");
    auto* pmmaMaterial = nist->FindOrBuildMaterial("G4_PLEXIGLASS");
    auto* airMaterial = nist->FindOrBuildMaterial("G4_AIR");

    auto* worldSolid = new G4Box("WorldSolid",
                                 kWorldHalfLength * mm,
                                 kWorldHalfLength * mm,
                                 kWorldHalfLength * mm);
    auto* worldLogical =
        new G4LogicalVolume(worldSolid, worldMaterial, "WorldLogical");

    auto* worldPhysical = new G4PVPlacement(nullptr,
                                            G4ThreeVector(),
                                            worldLogical,
                                            "WorldPhysical",
                                            nullptr,
                                            false,
                                            0,
                                            true);

    auto* pmmaSolid = new G4Box("PMMASolid",
                                0.5 * kPmmaSizeX * mm,
                                0.5 * kPmmaSizeY * mm,
                                0.5 * kPmmaSizeZ * mm);
    auto* pmmaLogical =
        new G4LogicalVolume(pmmaSolid, pmmaMaterial, "PMMALogical");

    new G4PVPlacement(nullptr,
                      G4ThreeVector(0.0, 0.0, kPmmaCenterZ * mm),
                      pmmaLogical,
                      "PMMAPhysical",
                      worldLogical,
                      false,
                      0,
                      true);

    if (config_ == nullptr || config_->enableAirDefect) {
        auto* airDefectSolid = new G4Tubs("AirDefectSolid",
                                          0.0,
                                          kAirDefectRadius * mm,
                                          kAirDefectHalfLength * mm,
                                          0.0,
                                          360.0 * deg);
        auto* airDefectLogical =
            new G4LogicalVolume(airDefectSolid,
                                airMaterial,
                                "AirDefectLogical");

        new G4PVPlacement(nullptr,
                          G4ThreeVector(
                              0.0,
                              0.0,
                              (kAirDefectCenterZ - kPmmaCenterZ) * mm),
                          airDefectLogical,
                          "AirDefectPhysical",
                          pmmaLogical,
                          false,
                          0,
                          true);

        auto* airVis = new G4VisAttributes(G4Colour(0.1, 0.6, 1.0, 0.35));
        airVis->SetForceSolid(true);
        airDefectLogical->SetVisAttributes(airVis);
    }

    auto* pmmaVis = new G4VisAttributes(G4Colour(0.9, 0.9, 0.95, 0.35));
    pmmaVis->SetForceSolid(true);
    pmmaLogical->SetVisAttributes(pmmaVis);

    BuildDetectorPlaneVis(detectorPlaneConfigs_[0],
                          "",
                          worldLogical,
                          worldMaterial);
    BuildDetectorPlaneVis(detectorPlaneConfigs_[1],
                          "Mirror",
                          worldLogical,
                          worldMaterial);

    if (config_ != nullptr && config_->enableCollimator) {
        auto* tungstenMaterial = nist->FindOrBuildMaterial("G4_W");
        const CollimatorProfile profile =
            CollimatorProfileReader().ReadProfile(config_->collimatorProfileFile,
                                                  config_->collimatorProfileId);
        CollimatorBuilder().Build(profile, worldLogical, tungstenMaterial);
    }

    worldLogical->SetVisAttributes(G4VisAttributes::GetInvisible());

    return worldPhysical;
}

const std::array<DetectorPlaneConfig, 2>&
DetectorConstruction::GetDetectorPlaneConfigs() const
{
    return detectorPlaneConfigs_;
}

#include "DetectorConstruction.hh"

#include "G4Box.hh"
#include "G4LogicalVolume.hh"
#include "G4NistManager.hh"
#include "G4PVPlacement.hh"
#include "G4SystemOfUnits.hh"
#include "G4ThreeVector.hh"

G4VPhysicalVolume* DetectorConstruction::Construct()
{
    auto* nist = G4NistManager::Instance();
    auto* worldMaterial = nist->FindOrBuildMaterial("G4_Galactic");

    auto* worldSolid = new G4Box("WorldSolid", 0.5 * m, 0.5 * m, 0.5 * m);
    auto* worldLogical =
        new G4LogicalVolume(worldSolid, worldMaterial, "WorldLogical");

    return new G4PVPlacement(nullptr,
                             G4ThreeVector(),
                             worldLogical,
                             "WorldPhysical",
                             nullptr,
                             false,
                             0,
                             true);
}

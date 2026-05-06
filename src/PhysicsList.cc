#include "PhysicsList.hh"

#include "G4EmLivermorePhysics.hh"
#include "G4SystemOfUnits.hh"

PhysicsList::PhysicsList()
{
    SetVerboseLevel(1);
    SetDefaultCutValue(0.1 * mm);
    RegisterPhysics(new G4EmLivermorePhysics);
}

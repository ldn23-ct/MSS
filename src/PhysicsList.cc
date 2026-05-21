#include "PhysicsList.hh"

#include "G4EmLivermorePhysics.hh"
#include "G4SystemOfUnits.hh"

PhysicsList::PhysicsList()
{
    RegisterPhysics(new G4EmLivermorePhysics());
    SetDefaultCutValue(0.1 * mm);
}

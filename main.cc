#include "ActionInitialization.hh"
#include "DetectorConstruction.hh"
#include "PhysicsList.hh"
#include "SimulationConfig.hh"
#include "SimulationMessenger.hh"

#include "G4RunManager.hh"
#include "G4RunManagerFactory.hh"
#include "G4UIExecutive.hh"
#include "G4UImanager.hh"
#include "G4VisExecutive.hh"

#include <memory>
#include <string>

int main(int argc, char** argv)
{
    auto runManager = std::unique_ptr<G4RunManager>(
        G4RunManagerFactory::CreateRunManager(G4RunManagerType::Default));

    auto config = std::make_shared<SimulationConfig>();

    auto* detectorConstruction = new DetectorConstruction(config);
    runManager->SetUserInitialization(detectorConstruction);
    runManager->SetUserInitialization(new PhysicsList);
    runManager->SetUserInitialization(
        new ActionInitialization(config,
                                 detectorConstruction->GetDetectorPlaneConfig()));

    SimulationMessenger messenger(config);

    auto* visManager = new G4VisExecutive();
    visManager -> Initialize();

    auto* uiManager = G4UImanager::GetUIpointer();
    if (argc > 1) {
        const std::string command = "/control/execute ";
        uiManager->ApplyCommand(command + argv[1]);
    } else {
        auto ui = std::make_unique<G4UIExecutive>(argc, argv);
        ui->SessionStart();
    }

    delete visManager;
    return 0;
}

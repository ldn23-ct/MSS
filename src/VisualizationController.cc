#include "VisualizationController.hh"

#include "ActionInitialization.hh"
#include "DetectorConstruction.hh"
#include "PhysicsList.hh"

#include "G4RunManager.hh"
#include "G4RunManagerFactory.hh"
#include "G4UIExecutive.hh"
#include "G4UImanager.hh"
#include "G4VisExecutive.hh"
#include "Randomize.hh"

#include <iostream>
#include <memory>
#include <stdexcept>

void VisualizationController::Execute(const SimulationConfig& config,
                                      const VehicleROIConfig& vehicleROI,
                                      const PoseList& poses) const
{
    if (poses.empty()) {
        throw std::runtime_error("no scan poses were generated for visualization");
    }

    const ScanPose& pose = poses.front();
    if (poses.size() > 1) {
        std::cout << "MSS --ui visualization uses the first pose only: "
                  << pose.pose_id << " (pose_index=" << pose.pose_index << ")\n";
    } else {
        std::cout << "MSS --ui visualization pose: " << pose.pose_id << "\n";
    }
    std::cout << "MSS --ui is visualization-only and does not write CSV or metadata output.\n";

    CLHEP::HepRandom::setTheSeed(pose.random_seed);

    auto* detectorConstruction = new DetectorConstruction(config, vehicleROI, pose);
    std::unique_ptr<G4RunManager> runManager(
        G4RunManagerFactory::CreateRunManager(G4RunManagerType::Default, 1));
    runManager->SetUserInitialization(detectorConstruction);
    runManager->SetUserInitialization(new PhysicsList());
    runManager->SetUserInitialization(new ActionInitialization(
        config,
        pose,
        vehicleROI,
        &detectorConstruction->GetRegionResolver(),
        ActionInitialization::Mode::Visualization));
    runManager->Initialize();

    auto visManager = std::make_unique<G4VisExecutive>();
    visManager->Initialize();

    char appName[] = "MSS";
    char* uiArgv[] = {appName};
    G4UIExecutive ui(1, uiArgv);

    auto* uiManager = G4UImanager::GetUIpointer();
    if (uiManager == nullptr) {
        throw std::runtime_error("failed to get Geant4 UI manager");
    }

    const G4int macroStatus = uiManager->ApplyCommand("/control/execute macros/vis.mac");
    if (macroStatus != 0) {
        throw std::runtime_error("failed to execute visualization macro: macros/vis.mac");
    }

    ui.SessionStart();
}

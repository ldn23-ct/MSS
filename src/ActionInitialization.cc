#include "ActionInitialization.hh"

#include "PrimaryGeneratorAction.hh"

#include <stdexcept>

ActionInitialization::ActionInitialization(const SimulationConfig& config)
    : ActionInitialization(config, ScanPoseManager().Generate(config).front())
{
}

ActionInitialization::ActionInitialization(const SimulationConfig& config, const ScanPose& pose)
    : hasConfig_(true), config_(config), pose_(pose)
{
}

void ActionInitialization::BuildForMaster() const {}

void ActionInitialization::Build() const
{
    if (!hasConfig_) {
        throw std::runtime_error("ActionInitialization requires SimulationConfig and ScanPose for M7 primary generation");
    }

    SetUserAction(new PrimaryGeneratorAction(config_.source, pose_));
}

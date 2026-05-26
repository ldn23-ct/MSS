#include "ActionInitialization.hh"

#include "EventAction.hh"
#include "PrimaryGeneratorAction.hh"
#include "SteppingAction.hh"

#include <stdexcept>

ActionInitialization::ActionInitialization(const SimulationConfig& config)
    : ActionInitialization(config, ScanPoseManager().Generate(config).front())
{
}

ActionInitialization::ActionInitialization(const SimulationConfig& config, const ScanPose& pose)
    : ActionInitialization(config, pose, nullptr)
{
}

ActionInitialization::ActionInitialization(const SimulationConfig& config,
                                           const ScanPose& pose,
                                           const RegionResolver* regionResolver)
    : hasConfig_(true),
      config_(config),
      pose_(pose),
      detectorPlane_(VirtualDetectorPlane::CalculateActual(config.detector, pose)),
      regionResolver_(regionResolver)
{
}

void ActionInitialization::BuildForMaster() const {}

void ActionInitialization::Build() const
{
    if (!hasConfig_) {
        throw std::runtime_error("ActionInitialization requires SimulationConfig and ScanPose for M7 primary generation");
    }

    SetUserAction(new PrimaryGeneratorAction(config_.source, pose_));
    auto* eventAction = new EventAction();
    SetUserAction(eventAction);
    SetUserAction(new SteppingAction(eventAction, regionResolver_, detectorPlane_));
}

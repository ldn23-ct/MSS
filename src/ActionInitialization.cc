#include "ActionInitialization.hh"

#include "EventAction.hh"
#include "PrimaryGeneratorAction.hh"
#include "RunAction.hh"
#include "SteppingAction.hh"

#include <stdexcept>

ActionInitialization::ActionInitialization(const SimulationConfig& config)
    : ActionInitialization(config, ScanPoseManager().Generate(config).front())
{
}

ActionInitialization::ActionInitialization(const SimulationConfig& config, const ScanPose& pose)
    : ActionInitialization(config, pose, VehicleROIConfig{}, nullptr)
{
}

ActionInitialization::ActionInitialization(const SimulationConfig& config,
                                           const ScanPose& pose,
                                           const VehicleROIConfig& vehicleROI)
    : ActionInitialization(config, pose, vehicleROI, nullptr)
{
}

ActionInitialization::ActionInitialization(const SimulationConfig& config,
                                           const ScanPose& pose,
                                           const VehicleROIConfig& vehicleROI,
                                           const RegionResolver* regionResolver,
                                           Mode mode)
    : hasConfig_(true),
      config_(config),
      vehicleROI_(vehicleROI),
      pose_(pose),
      detectorPlane_(VirtualDetectorPlane::CalculateActual(config.detector, pose)),
      regionResolver_(regionResolver),
      mode_(mode)
{
}

void ActionInitialization::BuildForMaster() const
{
    if (!hasConfig_) {
        throw std::runtime_error("ActionInitialization requires SimulationConfig and ScanPose for master RunAction");
    }

    if (mode_ == Mode::Visualization) {
        return;
    }

    if (config_.run.number_of_threads > 1) {
        SetUserAction(new RunAction(config_, vehicleROI_, pose_, RunAction::OutputRole::Master));
    }
}

void ActionInitialization::Build() const
{
    if (!hasConfig_) {
        throw std::runtime_error("ActionInitialization requires SimulationConfig and ScanPose for M7 primary generation");
    }

    SetUserAction(new PrimaryGeneratorAction(config_.source, pose_));
    if (mode_ == Mode::Visualization) {
        return;
    }

    const auto role = (config_.run.number_of_threads > 1)
                          ? RunAction::OutputRole::Worker
                          : RunAction::OutputRole::Serial;
    auto* runAction = new RunAction(config_, vehicleROI_, pose_, role);
    SetUserAction(runAction);
    auto* eventAction = new EventAction(runAction->Writer(), runAction->PhaseSpaceWriter());
    SetUserAction(eventAction);
    SetUserAction(new SteppingAction(eventAction, regionResolver_, detectorPlane_));
}

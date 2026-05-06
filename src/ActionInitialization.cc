#include "ActionInitialization.hh"

#include "EventAction.hh"
#include "PrimaryGeneratorAction.hh"
#include "RunAction.hh"
#include "SteppingAction.hh"

#include <utility>

ActionInitialization::ActionInitialization(
    std::shared_ptr<SimulationConfig> config,
    const DetectorPlaneConfig& detectorPlaneConfig)
    : config_(std::move(config)),
      detectorPlaneConfig_(detectorPlaneConfig)
{
}

void ActionInitialization::BuildForMaster() const
{
    SetUserAction(new RunAction(config_));
}

void ActionInitialization::Build() const
{
    SetUserAction(new RunAction(config_));
    auto* eventAction = new EventAction;
    SetUserAction(new PrimaryGeneratorAction(config_, eventAction));
    SetUserAction(eventAction);
    SetUserAction(new SteppingAction(eventAction, detectorPlaneConfig_));
}

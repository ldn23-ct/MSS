#include "ActionInitialization.hh"

#include "CsvWriter.hh"
#include "EventAction.hh"
#include "PrimaryGeneratorAction.hh"
#include "RunAction.hh"
#include "SteppingAction.hh"

#include <memory>
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
    SetUserAction(new RunAction(config_, nullptr));
}

void ActionInitialization::Build() const
{
    auto csvWriter = std::make_shared<CsvWriter>();
    SetUserAction(new RunAction(config_, csvWriter));
    auto* eventAction = new EventAction(csvWriter);
    SetUserAction(new PrimaryGeneratorAction(config_, eventAction));
    SetUserAction(eventAction);
    SetUserAction(new SteppingAction(eventAction, detectorPlaneConfig_));
}

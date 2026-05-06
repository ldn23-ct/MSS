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
      csvWriter_(std::make_shared<CsvWriter>()),
      detectorPlaneConfig_(detectorPlaneConfig)
{
}

void ActionInitialization::BuildForMaster() const
{
    SetUserAction(new RunAction(config_, csvWriter_));
}

void ActionInitialization::Build() const
{
    SetUserAction(new RunAction(config_, csvWriter_));
    auto* eventAction = new EventAction(csvWriter_);
    SetUserAction(new PrimaryGeneratorAction(config_, eventAction));
    SetUserAction(eventAction);
    SetUserAction(new SteppingAction(eventAction, detectorPlaneConfig_));
}

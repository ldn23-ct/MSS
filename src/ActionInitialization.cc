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
    const std::array<DetectorPlaneConfig, 2>& detectorPlaneConfigs)
    : config_(std::move(config)),
      detectorPlaneConfigs_(detectorPlaneConfigs)
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
    SetUserAction(new PrimaryGeneratorAction(config_));
    SetUserAction(eventAction);
    SetUserAction(new SteppingAction(eventAction, detectorPlaneConfigs_));
}

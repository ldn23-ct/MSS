#include "ActionInitialization.hh"

#include "EventAction.hh"
#include "PrimaryGeneratorAction.hh"
#include "RunAction.hh"
#include "SteppingAction.hh"

#include <utility>

ActionInitialization::ActionInitialization(std::shared_ptr<SimulationConfig> config)
    : config_(std::move(config))
{
}

void ActionInitialization::BuildForMaster() const
{
    SetUserAction(new RunAction(config_));
}

void ActionInitialization::Build() const
{
    SetUserAction(new PrimaryGeneratorAction(config_));
    SetUserAction(new RunAction(config_));
    auto* eventAction = new EventAction;
    SetUserAction(eventAction);
    SetUserAction(new SteppingAction);
}

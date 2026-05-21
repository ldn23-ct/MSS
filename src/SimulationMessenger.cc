#include "SimulationMessenger.hh"

#include "SimulationConfig.hh"

#include "G4UIcmdWithAString.hh"
#include "G4UIdirectory.hh"

SimulationMessenger::SimulationMessenger(std::shared_ptr<SimulationConfig> config)
    : config_(std::move(config))
{
    mssDirectory_ = std::make_unique<G4UIdirectory>("/mss/");
    mssDirectory_->SetGuidance("MSS second-round compatibility commands.");

    configPathCommand_ = std::make_unique<G4UIcmdWithAString>("/mss/config", this);
    configPathCommand_->SetGuidance("Set the second-round YAML entry file path.");
    configPathCommand_->SetParameterName("configPath", false);
}

SimulationMessenger::~SimulationMessenger() = default;

void SimulationMessenger::SetNewValue(G4UIcommand* command, G4String newValue)
{
    if (command == configPathCommand_.get() && config_) {
        config_->configFilePath = newValue;
    }
}

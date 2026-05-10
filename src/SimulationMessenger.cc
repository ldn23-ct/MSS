#include "SimulationMessenger.hh"

#include "SimulationConfig.hh"

#include "G4Exception.hh"
#include "G4ApplicationState.hh"
#ifdef G4MULTITHREADED
#include "G4MTRunManager.hh"
#endif
#include "G4RunManager.hh"
#include "G4SystemOfUnits.hh"
#include "G4UIcmdWithABool.hh"
#include "G4UIcmdWithADoubleAndUnit.hh"
#include "G4UIcmdWithAString.hh"
#include "G4UIcmdWithAnInteger.hh"
#include "G4UIcommandTree.hh"
#include "G4UIdirectory.hh"
#include "G4UImanager.hh"

#include <cerrno>
#include <cstdlib>
#include <memory>
#include <string>
#include <utility>

namespace {

void ReportMessengerError(const std::string& message)
{
    G4Exception("SimulationMessenger",
                "MSSConfig002",
                FatalException,
                message.c_str());
}

std::string Trim(G4String value)
{
    std::string text = value;
    const auto begin = text.find_first_not_of(" \t\r\n");
    if (begin == std::string::npos) {
        return "";
    }

    const auto end = text.find_last_not_of(" \t\r\n");
    text = text.substr(begin, end - begin + 1);
    if (text == "\"\"" || text == "''") {
        return "";
    }

    return text;
}

long ParseLong(const G4String& value, const char* fieldName)
{
    const std::string text = Trim(value);
    if (text.empty()) {
        ReportMessengerError(std::string(fieldName) + " must not be empty.");
    }

    char* end = nullptr;
    errno = 0;
    const long parsed = std::strtol(text.c_str(), &end, 10);
    if (errno != 0 || end == text.c_str() || *end != '\0') {
        ReportMessengerError(std::string(fieldName) + " must be an integer.");
    }

    return parsed;
}

bool HasUiCommand(const char* path)
{
    auto* uiManager = G4UImanager::GetUIpointer();
    if (uiManager == nullptr || uiManager->GetTree() == nullptr) {
        return false;
    }

    return uiManager->GetTree()->FindPath(path) != nullptr;
}

void TrySetRunManagerThreads(int numberOfThreads)
{
#ifdef G4MULTITHREADED
    auto* runManager = G4RunManager::GetRunManager();
    auto* mtRunManager = dynamic_cast<G4MTRunManager*>(runManager);
    if (mtRunManager != nullptr) {
        mtRunManager->SetNumberOfThreads(numberOfThreads);
    }
#else
    (void)numberOfThreads;
#endif
}

} // namespace

SimulationMessenger::SimulationMessenger(std::shared_ptr<SimulationConfig> config)
    : config_(std::move(config))
{
    geometryDirectory_ = std::make_unique<G4UIdirectory>("/geometry/");
    geometryDirectory_->SetGuidance("Geometry configuration.");

    sourceDirectory_ = std::make_unique<G4UIdirectory>("/source/");
    sourceDirectory_->SetGuidance("Primary source configuration.");

    outputDirectory_ = std::make_unique<G4UIdirectory>("/output/");
    outputDirectory_->SetGuidance("Output configuration.");

    collimatorProfileFileCommand_ =
        std::make_unique<G4UIcmdWithAString>("/geometry/collimatorProfileFile", this);
    collimatorProfileFileCommand_->SetGuidance("Set collimator profile CSV file.");
    collimatorProfileFileCommand_->AvailableForStates(G4State_PreInit);

    collimatorProfileIdCommand_ =
        std::make_unique<G4UIcmdWithAString>("/geometry/collimatorProfileId", this);
    collimatorProfileIdCommand_->SetGuidance("Set selected collimator profile ID.");
    collimatorProfileIdCommand_->AvailableForStates(G4State_PreInit);

    enableCollimatorCommand_ =
        std::make_unique<G4UIcmdWithABool>("/geometry/enableCollimator", this);
    enableCollimatorCommand_->SetGuidance("Enable or disable tungsten collimator construction.");
    enableCollimatorCommand_->AvailableForStates(G4State_PreInit);

    enableAirDefectCommand_ =
        std::make_unique<G4UIcmdWithABool>("/geometry/enableAirDefect", this);
    enableAirDefectCommand_->SetGuidance("Enable or disable the air defect.");
    enableAirDefectCommand_->AvailableForStates(G4State_PreInit);

    energyModeCommand_ =
        std::make_unique<G4UIcmdWithAString>("/source/energyMode", this);
    energyModeCommand_->SetGuidance("Set source energy mode: mono or spectrum.");

    monoEnergyCommand_ =
        std::make_unique<G4UIcmdWithADoubleAndUnit>("/source/monoEnergy", this);
    monoEnergyCommand_->SetGuidance("Set mono source energy.");
    monoEnergyCommand_->SetUnitCategory("Energy");
    monoEnergyCommand_->SetDefaultUnit("keV");

    spectrumFileCommand_ =
        std::make_unique<G4UIcmdWithAString>("/source/spectrumFile", this);
    spectrumFileCommand_->SetGuidance("Set source spectrum CSV file.");

    randomSeedCommand_ =
        std::make_unique<G4UIcmdWithAString>("/run/randomSeed", this);
    randomSeedCommand_->SetGuidance("Set random seed.");

    if (!HasUiCommand("/run/numberOfThreads")) {
        numberOfThreadsCommand_ =
            std::make_unique<G4UIcmdWithAnInteger>("/run/numberOfThreads", this);
        numberOfThreadsCommand_->SetGuidance("Set Geant4 worker thread count.");
    }

    outputDirectoryCommand_ =
        std::make_unique<G4UIcmdWithAString>("/output/directory", this);
    outputDirectoryCommand_->SetGuidance("Set output directory.");

    debugOutputCommand_ =
        std::make_unique<G4UIcmdWithABool>("/output/debug", this);
    debugOutputCommand_->SetGuidance("Explicitly enable or disable debug output.");
}

SimulationMessenger::~SimulationMessenger() = default;

void SimulationMessenger::SetNewValue(G4UIcommand* command, G4String newValue)
{
    if (command == collimatorProfileFileCommand_.get()) {
        config_->collimatorProfileFile = Trim(newValue);
    } else if (command == collimatorProfileIdCommand_.get()) {
        config_->collimatorProfileId = Trim(newValue);
    } else if (command == enableCollimatorCommand_.get()) {
        config_->enableCollimator =
            enableCollimatorCommand_->GetNewBoolValue(newValue);
    } else if (command == enableAirDefectCommand_.get()) {
        config_->enableAirDefect =
            enableAirDefectCommand_->GetNewBoolValue(newValue);
    } else if (command == energyModeCommand_.get()) {
        config_->energyMode = Trim(newValue);
    } else if (command == monoEnergyCommand_.get()) {
        config_->monoEnergy_keV =
            monoEnergyCommand_->GetNewDoubleValue(newValue) / keV;
    } else if (command == spectrumFileCommand_.get()) {
        config_->spectrumFile = Trim(newValue);
    } else if (command == randomSeedCommand_.get()) {
        config_->randomSeed = ParseLong(newValue, "randomSeed");
    } else if (command == numberOfThreadsCommand_.get()) {
        const int threads = numberOfThreadsCommand_->GetNewIntValue(newValue);
        config_->numberOfThreads = threads;
        TrySetRunManagerThreads(threads);
    } else if (command == outputDirectoryCommand_.get()) {
        config_->outputDirectory = Trim(newValue);
    } else if (command == debugOutputCommand_.get()) {
        config_->debugOutputOverride = debugOutputCommand_->GetNewBoolValue(newValue);
    }

    config_->Validate();
}

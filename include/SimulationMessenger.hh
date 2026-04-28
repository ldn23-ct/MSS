#ifndef SIMULATION_MESSENGER_HH
#define SIMULATION_MESSENGER_HH

#include "G4UImessenger.hh"

#include <memory>

class G4UIcmdWithABool;
class G4UIcmdWithADoubleAndUnit;
class G4UIcmdWithAString;
class G4UIcmdWithAnInteger;
class G4UIdirectory;
class G4UIcommand;
struct SimulationConfig;

class SimulationMessenger : public G4UImessenger {
  public:
    explicit SimulationMessenger(std::shared_ptr<SimulationConfig> config);
    ~SimulationMessenger() override;

    void SetNewValue(G4UIcommand* command, G4String newValue) override;

  private:
    std::shared_ptr<SimulationConfig> config_;

    std::unique_ptr<G4UIdirectory> geometryDirectory_;
    std::unique_ptr<G4UIdirectory> sourceDirectory_;
    std::unique_ptr<G4UIdirectory> outputDirectory_;

    std::unique_ptr<G4UIcmdWithAString> collimatorProfileFileCommand_;
    std::unique_ptr<G4UIcmdWithAString> collimatorProfileIdCommand_;
    std::unique_ptr<G4UIcmdWithABool> enableAirDefectCommand_;

    std::unique_ptr<G4UIcmdWithAString> energyModeCommand_;
    std::unique_ptr<G4UIcmdWithADoubleAndUnit> monoEnergyCommand_;
    std::unique_ptr<G4UIcmdWithAString> spectrumFileCommand_;

    std::unique_ptr<G4UIcmdWithAString> randomSeedCommand_;
    std::unique_ptr<G4UIcmdWithAnInteger> numberOfThreadsCommand_;

    std::unique_ptr<G4UIcmdWithAString> outputDirectoryCommand_;
    std::unique_ptr<G4UIcmdWithABool> debugOutputCommand_;
};

#endif

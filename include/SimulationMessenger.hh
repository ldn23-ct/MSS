#ifndef SIMULATION_MESSENGER_HH
#define SIMULATION_MESSENGER_HH

#include "G4UImessenger.hh"

#include <memory>

class G4UIcmdWithAString;
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
    std::unique_ptr<G4UIdirectory> mssDirectory_;
    std::unique_ptr<G4UIcmdWithAString> configPathCommand_;
};

#endif

#ifndef RUN_ACTION_HH
#define RUN_ACTION_HH

#include "G4UserRunAction.hh"

#include <memory>

class G4Run;
struct SimulationConfig;

class RunAction : public G4UserRunAction {
  public:
    explicit RunAction(std::shared_ptr<SimulationConfig> config);
    ~RunAction() override = default;

    void BeginOfRunAction(const G4Run* run) override;
    void EndOfRunAction(const G4Run* run) override;

    int GetEffectiveNumberOfThreads() const;

  private:
    std::shared_ptr<SimulationConfig> config_;
};

#endif

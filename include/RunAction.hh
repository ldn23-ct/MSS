#ifndef RUN_ACTION_HH
#define RUN_ACTION_HH

#include "G4UserRunAction.hh"

#include <memory>

class CsvWriter;
class G4Run;
struct SimulationConfig;

class RunAction : public G4UserRunAction {
  public:
    RunAction(std::shared_ptr<SimulationConfig> config,
              std::shared_ptr<CsvWriter> csvWriter,
              double pmmaThicknessMm);
    ~RunAction() override = default;

    void BeginOfRunAction(const G4Run* run) override;
    void EndOfRunAction(const G4Run* run) override;

    int GetEffectiveNumberOfThreads() const;

  private:
    std::shared_ptr<SimulationConfig> config_;
    std::shared_ptr<CsvWriter> csvWriter_;
    double pmmaThicknessMm_;
};

#endif

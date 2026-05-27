#ifndef RUN_ACTION_HH
#define RUN_ACTION_HH

#include "CsvWriter.hh"
#include "ScanPoseManager.hh"
#include "SimulationConfig.hh"

#include "G4UserRunAction.hh"

#include <string>

class G4Run;

class RunAction : public G4UserRunAction {
  public:
    RunAction() = default;
    RunAction(SimulationConfig config, ScanPose pose);
    ~RunAction() override = default;

    void BeginOfRunAction(const G4Run* run) override;
    void EndOfRunAction(const G4Run* run) override;

    CsvWriter* Writer();

  private:
    std::string BuildRunId() const;
    std::string OutputCsvName() const;
    std::string OutputCsvPath() const;
    void PrepareOutputDirectory() const;

    bool configured_ = false;
    SimulationConfig config_;
    ScanPose pose_;
    CsvWriter writer_;
};

#endif

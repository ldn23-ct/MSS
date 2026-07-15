#ifndef RUN_ACTION_HH
#define RUN_ACTION_HH

#include "CsvWriter.hh"
#include "MetadataWriter.hh"
#include "ScanPoseManager.hh"
#include "SimulationConfig.hh"
#include "VehicleROIConfig.hh"

#include "G4UserRunAction.hh"

#include <string>
#include <vector>

class G4Run;

class RunAction : public G4UserRunAction {
  public:
    enum class OutputRole {
        Master,
        Worker,
        Serial
    };

    RunAction() = default;
    RunAction(SimulationConfig config,
              VehicleROIConfig vehicleROI,
              ScanPose pose,
              OutputRole role = OutputRole::Serial);
    ~RunAction() override = default;

    void BeginOfRunAction(const G4Run* run) override;
    void EndOfRunAction(const G4Run* run) override;

    CsvWriter* Writer();

  private:
    std::string BuildRunId() const;
    std::string OutputCsvName() const;
    std::string FinalCsvPath() const;
    std::string MetadataPath() const;
    std::string RunDirectory() const;
    std::string TmpDirectory() const;
    std::string TempCsvName(int threadId) const;
    std::string TempCsvPath(int threadId) const;
    std::vector<std::string> ExpectedTempCsvPaths() const;
    int CurrentThreadId() const;
    void PrepareRunOutputDirectory() const;
    void EnsureTmpDirectory() const;
    void MergeThreadCsvFiles();

    bool configured_ = false;
    OutputRole role_ = OutputRole::Serial;
    SimulationConfig config_;
    VehicleROIConfig vehicleROI_;
    ScanPose pose_;
    CsvWriter writer_;
    MetadataWriter metadataWriter_;
};

#endif

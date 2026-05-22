#ifndef ACTION_INITIALIZATION_HH
#define ACTION_INITIALIZATION_HH

#include "ScanPoseManager.hh"
#include "SimulationConfig.hh"

#include "G4VUserActionInitialization.hh"

class ActionInitialization : public G4VUserActionInitialization {
  public:
    ActionInitialization() = default;
    explicit ActionInitialization(const SimulationConfig& config);
    ActionInitialization(const SimulationConfig& config, const ScanPose& pose);
    ~ActionInitialization() override = default;

    void BuildForMaster() const override;
    void Build() const override;

  private:
    bool hasConfig_ = false;
    SimulationConfig config_;
    ScanPose pose_;
};

#endif

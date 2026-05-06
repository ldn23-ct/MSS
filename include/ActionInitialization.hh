#ifndef ACTION_INITIALIZATION_HH
#define ACTION_INITIALIZATION_HH

#include "DetectorConstruction.hh"

#include "G4VUserActionInitialization.hh"

#include <memory>

struct SimulationConfig;

class ActionInitialization : public G4VUserActionInitialization {
  public:
    ActionInitialization(std::shared_ptr<SimulationConfig> config,
                         const DetectorPlaneConfig& detectorPlaneConfig);
    ~ActionInitialization() override = default;

    void BuildForMaster() const override;
    void Build() const override;

  private:
    std::shared_ptr<SimulationConfig> config_;
    DetectorPlaneConfig detectorPlaneConfig_;
};

#endif

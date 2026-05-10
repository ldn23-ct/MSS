#ifndef ACTION_INITIALIZATION_HH
#define ACTION_INITIALIZATION_HH

#include "DetectorConstruction.hh"

#include "G4VUserActionInitialization.hh"

#include <array>
#include <memory>

struct SimulationConfig;

class ActionInitialization : public G4VUserActionInitialization {
  public:
    ActionInitialization(std::shared_ptr<SimulationConfig> config,
                         const std::array<DetectorPlaneConfig, 2>& detectorPlaneConfigs);
    ~ActionInitialization() override = default;

    void BuildForMaster() const override;
    void Build() const override;

  private:
    std::shared_ptr<SimulationConfig> config_;
    std::array<DetectorPlaneConfig, 2> detectorPlaneConfigs_;
};

#endif

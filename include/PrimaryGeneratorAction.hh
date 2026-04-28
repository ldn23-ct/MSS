#ifndef PRIMARY_GENERATOR_ACTION_HH
#define PRIMARY_GENERATOR_ACTION_HH

#include "G4VUserPrimaryGeneratorAction.hh"

#include <memory>

class G4Event;
struct SimulationConfig;

class PrimaryGeneratorAction : public G4VUserPrimaryGeneratorAction {
  public:
    explicit PrimaryGeneratorAction(std::shared_ptr<const SimulationConfig> config);
    ~PrimaryGeneratorAction() override = default;

    void GeneratePrimaries(G4Event* event) override;

  private:
    std::shared_ptr<const SimulationConfig> config_;
};

#endif

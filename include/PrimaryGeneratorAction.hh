#ifndef PRIMARY_GENERATOR_ACTION_HH
#define PRIMARY_GENERATOR_ACTION_HH

#include "SpectrumSampler.hh"

#include "G4VUserPrimaryGeneratorAction.hh"

#include <memory>

class EventAction;
class G4Event;
class G4ParticleGun;
struct SimulationConfig;

class PrimaryGeneratorAction : public G4VUserPrimaryGeneratorAction {
  public:
    explicit PrimaryGeneratorAction(std::shared_ptr<const SimulationConfig> config,
                                    EventAction* eventAction = nullptr);
    ~PrimaryGeneratorAction() override;

    void GeneratePrimaries(G4Event* event) override;

  private:
    double SelectInitialEnergyKeV();

    std::shared_ptr<const SimulationConfig> config_;
    EventAction* eventAction_ = nullptr;
    std::unique_ptr<G4ParticleGun> particleGun_;
    SpectrumSampler spectrumSampler_;
};

#endif

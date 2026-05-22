#ifndef PRIMARY_GENERATOR_ACTION_HH
#define PRIMARY_GENERATOR_ACTION_HH

#include "SourceModel.hh"

#include "G4VUserPrimaryGeneratorAction.hh"

#include <memory>

class G4Event;
class G4ParticleGun;

class PrimaryGeneratorAction : public G4VUserPrimaryGeneratorAction {
  public:
    PrimaryGeneratorAction(const SourceConfig& sourceConfig, const ScanPose& pose);
    ~PrimaryGeneratorAction() override;

    void GeneratePrimaries(G4Event* event) override;

  private:
    SourceModel sourceModel_;
    std::unique_ptr<G4ParticleGun> particleGun_;
};

#endif

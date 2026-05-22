#include "PrimaryGeneratorAction.hh"

#include "G4Event.hh"
#include "G4Gamma.hh"
#include "G4ParticleGun.hh"
#include "G4SystemOfUnits.hh"

#include <memory>
#include <stdexcept>

PrimaryGeneratorAction::PrimaryGeneratorAction(const SourceConfig& sourceConfig, const ScanPose& pose)
    : sourceModel_(sourceConfig, pose), particleGun_(std::make_unique<G4ParticleGun>(1))
{
    particleGun_->SetParticleDefinition(G4Gamma::GammaDefinition());
}

PrimaryGeneratorAction::~PrimaryGeneratorAction() = default;

void PrimaryGeneratorAction::GeneratePrimaries(G4Event* event)
{
    if (event == nullptr) {
        throw std::runtime_error("PrimaryGeneratorAction received a null G4Event");
    }

    const PrimarySample sample = sourceModel_.SamplePrimary();
    particleGun_->SetParticleDefinition(G4Gamma::GammaDefinition());
    particleGun_->SetParticlePosition(sample.position_mm * mm);
    particleGun_->SetParticleMomentumDirection(sample.direction);
    particleGun_->SetParticleEnergy(sample.energy_keV * keV);
    particleGun_->GeneratePrimaryVertex(event);
}

#include "PrimaryGeneratorAction.hh"

#include "SimulationConfig.hh"

#include "G4Event.hh"
#include "G4Exception.hh"
#include "G4Gamma.hh"
#include "G4ParticleGun.hh"
#include "G4SystemOfUnits.hh"
#include "G4ThreeVector.hh"
#include "Randomize.hh"

#include <cmath>
#include <string>
#include <utility>

namespace {

constexpr double kSourceZ_mm = -185.0;
constexpr double kTargetPlaneZ_mm = 0.0;
constexpr double kTargetDiskRadius_mm = 1.5;
constexpr double kTwoPi = 6.28318530717958647692;

void ReportPrimaryGeneratorError(const std::string& message)
{
    G4Exception("PrimaryGeneratorAction",
                "MSSPrimary001",
                FatalException,
                message.c_str());
}

} // namespace

PrimaryGeneratorAction::PrimaryGeneratorAction(
    std::shared_ptr<const SimulationConfig> config)
    : config_(std::move(config)),
      particleGun_(std::make_unique<G4ParticleGun>(1))
{
    particleGun_->SetParticleDefinition(G4Gamma::GammaDefinition());
    particleGun_->SetParticlePosition(G4ThreeVector(0.0, 0.0, kSourceZ_mm * mm));
}

PrimaryGeneratorAction::~PrimaryGeneratorAction() = default;

void PrimaryGeneratorAction::GeneratePrimaries(G4Event* event)
{
    if (config_ == nullptr) {
        ReportPrimaryGeneratorError("SimulationConfig is not available.");
    }
    config_->Validate();

    const double energy_keV = SelectInitialEnergyKeV();
    particleGun_->SetParticleEnergy(energy_keV * keV);
    particleGun_->SetParticlePosition(G4ThreeVector(0.0, 0.0, kSourceZ_mm * mm));

    const double radius = kTargetDiskRadius_mm * std::sqrt(G4UniformRand());
    const double angle = kTwoPi * G4UniformRand();
    const double targetX_mm = radius * std::cos(angle);
    const double targetY_mm = radius * std::sin(angle);

    const G4ThreeVector sourcePosition(0.0, 0.0, kSourceZ_mm * mm);
    const G4ThreeVector targetPosition(targetX_mm * mm,
                                       targetY_mm * mm,
                                       kTargetPlaneZ_mm * mm);
    particleGun_->SetParticleMomentumDirection(
        (targetPosition - sourcePosition).unit());

    particleGun_->GeneratePrimaryVertex(event);
}

double PrimaryGeneratorAction::SelectInitialEnergyKeV()
{
    if (config_->energyMode == "mono") {
        return config_->monoEnergy_keV;
    }

    if (config_->energyMode == "spectrum") {
        if (spectrumSampler_.LoadedFilePath() != config_->spectrumFile) {
            spectrumSampler_.Load(config_->spectrumFile);
        }
        return spectrumSampler_.SampleEnergyKeV();
    }

    ReportPrimaryGeneratorError("energyMode must be either 'mono' or 'spectrum'.");
    return 0.0;
}

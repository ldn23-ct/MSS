#include "PrimaryGeneratorAction.hh"

#include <utility>

PrimaryGeneratorAction::PrimaryGeneratorAction(
    std::shared_ptr<const SimulationConfig> config)
    : config_(std::move(config))
{
}

void PrimaryGeneratorAction::GeneratePrimaries(G4Event*)
{
}

#include "RunAction.hh"

#include "SimulationConfig.hh"

#ifdef G4MULTITHREADED
#include "G4MTRunManager.hh"
#include "G4Threading.hh"
#endif
#include "G4RunManager.hh"

#include <utility>

namespace {

bool IsConfigOwnerThread()
{
#ifdef G4MULTITHREADED
    return G4Threading::IsMasterThread();
#else
    return true;
#endif
}

} // namespace

RunAction::RunAction(std::shared_ptr<SimulationConfig> config)
    : config_(std::move(config))
{
}

void RunAction::BeginOfRunAction(const G4Run*)
{
    if (config_ != nullptr && IsConfigOwnerThread()) {
        config_->numberOfThreads = GetEffectiveNumberOfThreads();
        config_->Validate();
    }
}

void RunAction::EndOfRunAction(const G4Run*)
{
}

int RunAction::GetEffectiveNumberOfThreads() const
{
#ifdef G4MULTITHREADED
    auto* runManager = G4RunManager::GetRunManager();
    auto* mtRunManager = dynamic_cast<G4MTRunManager*>(runManager);
    if (mtRunManager != nullptr && mtRunManager->GetNumberOfThreads() > 0) {
        return mtRunManager->GetNumberOfThreads();
    }

    if (runManager != nullptr) {
        return 1;
    }
#else
    if (G4RunManager::GetRunManager() != nullptr) {
        return 1;
    }
#endif

    if (config_ != nullptr && config_->numberOfThreads > 0) {
        return config_->numberOfThreads;
    }

    return 1;
}

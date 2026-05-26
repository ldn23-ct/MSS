#include "SteppingAction.hh"

#include "EventAction.hh"
#include "G4ParticleDefinition.hh"
#include "G4Step.hh"
#include "G4StepPoint.hh"
#include "G4SystemOfUnits.hh"
#include "G4Track.hh"
#include "G4VPhysicalVolume.hh"
#include "G4VProcess.hh"
#include "RegionResolver.hh"

SteppingAction::SteppingAction(EventAction* eventAction, const RegionResolver* regionResolver)
    : eventAction_(eventAction), regionResolver_(regionResolver)
{
}

void SteppingAction::UserSteppingAction(const G4Step* step)
{
    if (step == nullptr || eventAction_ == nullptr) {
        return;
    }

    G4Track* track = step->GetTrack();
    if (track == nullptr || track->GetDefinition() == nullptr ||
        track->GetDefinition()->GetParticleName() != "gamma") {
        return;
    }

    const G4StepPoint* preStep = step->GetPreStepPoint();
    const G4StepPoint* postStep = step->GetPostStepPoint();
    const G4VPhysicalVolume* preStepVolume = (preStep != nullptr) ? preStep->GetPhysicalVolume() : nullptr;

    eventAction_->EnsureGammaTrackSummary(*track, preStepVolume, regionResolver_);

    if (postStep == nullptr || postStep->GetProcessDefinedStep() == nullptr) {
        return;
    }

    const G4String processName = postStep->GetProcessDefinedStep()->GetProcessName();
    if (processName != "compt" && processName != "Rayl") {
        return;
    }

    const G4ThreeVector scatterPosMm = postStep->GetPosition() / mm;
    const std::string regionId = (regionResolver_ != nullptr)
                                     ? regionResolver_->ResolvePreStepVolume(preStepVolume)
                                     : (preStepVolume != nullptr ? "other" : "none");

    if (processName == "compt") {
        eventAction_->RecordComptonScatter(track->GetTrackID(), scatterPosMm, regionId);
    } else {
        eventAction_->RecordRayleighScatter(track->GetTrackID(), scatterPosMm, regionId);
    }
}

#include "SteppingAction.hh"

#include "EventAction.hh"

#include "G4LogicalVolume.hh"
#include "G4ParticleDefinition.hh"
#include "G4Step.hh"
#include "G4StepPoint.hh"
#include "G4SystemOfUnits.hh"
#include "G4Track.hh"
#include "G4VPhysicalVolume.hh"
#include "G4VProcess.hh"

namespace {

bool IsPrimaryGamma(const G4Track* track)
{
    return track != nullptr
           && track->GetDefinition() != nullptr
           && track->GetDefinition()->GetParticleName() == "gamma"
           && track->GetTrackID() == 1
           && track->GetParentID() == 0;
}

bool IsPmmaStep(const G4StepPoint* preStepPoint)
{
    if (preStepPoint == nullptr
        || preStepPoint->GetPhysicalVolume() == nullptr
        || preStepPoint->GetPhysicalVolume()->GetLogicalVolume() == nullptr) {
        return false;
    }

    return preStepPoint->GetPhysicalVolume()->GetLogicalVolume()->GetName()
           == "PMMALogical";
}

const G4VProcess* GetPostStepProcess(const G4StepPoint* postStepPoint)
{
    return postStepPoint != nullptr
               ? postStepPoint->GetProcessDefinedStep()
               : nullptr;
}

} // namespace

SteppingAction::SteppingAction(
    EventAction* eventAction,
    const DetectorPlaneConfig& detectorPlaneConfig)
    : eventAction_(eventAction),
      detectorPlaneConfig_(detectorPlaneConfig)
{
}

void SteppingAction::UserSteppingAction(const G4Step* step)
{
    if (step == nullptr || eventAction_ == nullptr) {
        return;
    }

    const auto* track = step->GetTrack();
    if (!IsPrimaryGamma(track)) {
        return;
    }

    const auto* preStepPoint = step->GetPreStepPoint();
    const auto* postStepPoint = step->GetPostStepPoint();
    if (preStepPoint == nullptr || postStepPoint == nullptr) {
        return;
    }

    if (IsPmmaStep(preStepPoint)) {
        const auto* process = GetPostStepProcess(postStepPoint);
        if (process != nullptr) {
            const auto& processName = process->GetProcessName();
            const auto position = postStepPoint->GetPosition();
            if (processName == "compt") {
                eventAction_->RecordComptonScatter(position);
            } else if (processName == "Rayl") {
                eventAction_->RecordRayleighScatter(position);
            }
        }
    }

    if (eventAction_->HasDetectorHit()) {
        return;
    }

    const auto prePosition = preStepPoint->GetPosition();
    const auto postPosition = postStepPoint->GetPosition();
    const auto direction = preStepPoint->GetMomentumDirection();

    const double detectorZ = detectorPlaneConfig_.z_mm * mm;
    if (prePosition.z() <= detectorZ
        || postPosition.z() > detectorZ
        || direction.z() >= 0.0) {
        return;
    }

    const double t =
        (detectorZ - prePosition.z()) / (postPosition.z() - prePosition.z());
    const double detX = prePosition.x() + t * (postPosition.x() - prePosition.x());
    const double detY = prePosition.y() + t * (postPosition.y() - prePosition.y());

    const double detX_mm = detX / mm;
    const double detY_mm = detY / mm;
    if (detX_mm < detectorPlaneConfig_.x_min_mm
        || detX_mm > detectorPlaneConfig_.x_max_mm
        || detY_mm < detectorPlaneConfig_.y_min_mm
        || detY_mm > detectorPlaneConfig_.y_max_mm) {
        return;
    }

    DetectorHitRecord hit;
    hit.det_x = detX_mm;
    hit.det_y = detY_mm;
    hit.det_z = detectorPlaneConfig_.z_mm;
    hit.det_energy_keV = postStepPoint->GetKineticEnergy() / keV;
    hit.det_dir = direction;
    eventAction_->RecordDetectorHit(hit);
}

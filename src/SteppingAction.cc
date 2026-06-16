#include "SteppingAction.hh"

#include "EventAction.hh"
#include "G4ParticleDefinition.hh"
#include "G4Step.hh"
#include "G4StepPoint.hh"
#include "G4SystemOfUnits.hh"
#include "G4Track.hh"
#include "G4ThreeVector.hh"
#include "G4VPhysicalVolume.hh"
#include "G4VProcess.hh"
#include "RegionResolver.hh"

SteppingAction::SteppingAction(EventAction* eventAction,
                               const RegionResolver* regionResolver,
                               const DetectorPlaneActual& detectorPlane)
    : eventAction_(eventAction), regionResolver_(regionResolver), detectorPlane_(detectorPlane)
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

    if (!eventAction_->HasDetectorHit(track->GetTrackID())) {
        TryRecordDetectorCrossing(*step, *track);
    }

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

bool SteppingAction::TryRecordDetectorCrossing(const G4Step& step, const G4Track& track)
{
    const G4StepPoint* preStep = step.GetPreStepPoint();
    const G4StepPoint* postStep = step.GetPostStepPoint();
    if (preStep == nullptr || postStep == nullptr) {
        return false;
    }

    const G4ThreeVector prePosMm = preStep->GetPosition() / mm;
    const G4ThreeVector postPosMm = postStep->GetPosition() / mm;
    if (prePosMm.z() <= detectorPlane_.z_mm || postPosMm.z() > detectorPlane_.z_mm) {
        return false;
    }

    if (preStep->GetMomentumDirection().z() >= 0.0) {
        return false;
    }

    const double dz = postPosMm.z() - prePosMm.z();
    if (dz == 0.0) {
        return false;
    }

    const double t = (detectorPlane_.z_mm - prePosMm.z()) / dz;
    const double detX = prePosMm.x() + t * (postPosMm.x() - prePosMm.x());
    const double detY = prePosMm.y() + t * (postPosMm.y() - prePosMm.y());
    if (!IsInsideDetectorBounds(detX, detY)) {
        return false;
    }

    DetectorHitRecord hit;
    hit.det_x_mm = detX;
    hit.det_y_mm = detY;
    hit.det_z_mm = detectorPlane_.z_mm;
    hit.det_energy_keV = preStep->GetKineticEnergy() / keV;
    hit.direction = preStep->GetMomentumDirection();
    hit.weight = track.GetWeight();
    eventAction_->RecordDetectorHit(track.GetTrackID(), hit);
    return eventAction_->HasDetectorHit(track.GetTrackID());
}

bool SteppingAction::IsInsideDetectorBounds(double x_mm, double y_mm) const
{
    return x_mm >= detectorPlane_.x_min_mm
        && x_mm <= detectorPlane_.x_max_mm
        && y_mm >= detectorPlane_.y_min_mm
        && y_mm <= detectorPlane_.y_max_mm;
}

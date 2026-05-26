#include "EventAction.hh"

#include "G4Event.hh"
#include "G4SystemOfUnits.hh"
#include "G4ThreeVector.hh"
#include "G4Track.hh"
#include "G4VProcess.hh"
#include "RegionResolver.hh"

void EventAction::BeginOfEventAction(const G4Event* event)
{
    record_ = EventRecord{};
    if (event != nullptr) {
        record_.event_id = event->GetEventID();
    }
}

void EventAction::EndOfEventAction(const G4Event*) {}

GammaTrackSummary& EventAction::EnsureGammaTrackSummary(const G4Track& track,
                                                        const G4VPhysicalVolume* sourceVolume,
                                                        const RegionResolver* resolver)
{
    const int trackId = track.GetTrackID();
    auto found = record_.gamma_tracks.find(trackId);
    if (found != record_.gamma_tracks.end()) {
        return found->second;
    }

    GammaTrackSummary summary;
    summary.track_id = trackId;
    summary.parent_id = track.GetParentID();
    summary.is_primary_gamma = (summary.track_id == 1 && summary.parent_id == 0);
    summary.gamma_source_pos = track.GetVertexPosition() / mm;

    if (summary.is_primary_gamma) {
        summary.gamma_source_type = "primary";
        summary.gamma_source_process = "primary_generator";
        summary.gamma_source_region_id = "source";
    } else {
        summary.gamma_source_type = "secondary";
        const G4VProcess* creator = track.GetCreatorProcess();
        summary.gamma_source_process = (creator != nullptr) ? creator->GetProcessName() : "none";
        summary.gamma_source_region_id = ResolveSourceRegion(sourceVolume, resolver);
    }

    const auto inserted = record_.gamma_tracks.emplace(trackId, summary);
    return inserted.first->second;
}

void EventAction::RecordComptonScatter(int track_id, const G4ThreeVector& pos, const std::string& region_id)
{
    auto found = record_.gamma_tracks.find(track_id);
    if (found == record_.gamma_tracks.end()) {
        return;
    }

    ++found->second.scatter.compton_count;
    RecordScatter(found->second, pos, region_id);
}

void EventAction::RecordRayleighScatter(int track_id, const G4ThreeVector& pos, const std::string& region_id)
{
    auto found = record_.gamma_tracks.find(track_id);
    if (found == record_.gamma_tracks.end()) {
        return;
    }

    ++found->second.scatter.rayleigh_count;
    RecordScatter(found->second, pos, region_id);
}

void EventAction::RecordDetectorHit(int track_id, const DetectorHitRecord& hit)
{
    auto found = record_.gamma_tracks.find(track_id);
    if (found == record_.gamma_tracks.end() || found->second.hit.detected) {
        return;
    }

    found->second.hit = hit;
    found->second.hit.detected = true;
}

bool EventAction::HasDetectorHit(int track_id) const
{
    const auto found = record_.gamma_tracks.find(track_id);
    return found != record_.gamma_tracks.end() && found->second.hit.detected;
}

const EventRecord& EventAction::GetRecord() const
{
    return record_;
}

const EventRecord& EventAction::CurrentRecord() const
{
    return GetRecord();
}

void EventAction::RecordScatter(GammaTrackSummary& summary,
                                const G4ThreeVector& pos,
                                const std::string& region_id)
{
    ++summary.scatter.scatter_count_total;

    if (summary.scatter.scatter_count_total == 1) {
        summary.scatter.first_scatter_pos = pos;
        summary.scatter.first_scatter_region_id = region_id;
    }

    summary.scatter.last_scatter_pos = pos;
    summary.scatter.last_scatter_region_id = region_id;
}

std::string EventAction::ResolveSourceRegion(const G4VPhysicalVolume* sourceVolume,
                                             const RegionResolver* resolver) const
{
    if (sourceVolume == nullptr) {
        return "none";
    }

    if (resolver == nullptr) {
        return "other";
    }

    return resolver->ResolvePreStepVolume(sourceVolume);
}

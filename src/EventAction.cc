#include "EventAction.hh"

#include "G4Event.hh"
#include "G4ThreeVector.hh"

void EventAction::BeginOfEventAction(const G4Event* event)
{
    record_ = EventRecord{};
    if (event != nullptr) {
        record_.event_id = event->GetEventID();
    }
}

void EventAction::EndOfEventAction(const G4Event*) {}

void EventAction::RecordComptonScatter(const G4ThreeVector& pos, const std::string& region_id)
{
    ++record_.scatter.compton_count;
    RecordScatter(pos, region_id);
}

void EventAction::RecordRayleighScatter(const G4ThreeVector& pos, const std::string& region_id)
{
    ++record_.scatter.rayleigh_count;
    RecordScatter(pos, region_id);
}

void EventAction::RecordDetectorHit(const DetectorHitRecord& hit)
{
    if (record_.hit.detected) {
        return;
    }

    record_.hit = hit;
    record_.hit.detected = true;
}

bool EventAction::HasDetectorHit() const
{
    return record_.hit.detected;
}

const EventRecord& EventAction::GetRecord() const
{
    return record_;
}

const EventRecord& EventAction::CurrentRecord() const
{
    return GetRecord();
}

void EventAction::RecordScatter(const G4ThreeVector& pos, const std::string& region_id)
{
    ++record_.scatter.scatter_count_total;

    if (record_.scatter.scatter_count_total == 1) {
        record_.scatter.first_scatter_pos = pos;
        record_.scatter.first_scatter_region_id = region_id;
    }

    record_.scatter.last_scatter_pos = pos;
    record_.scatter.last_scatter_region_id = region_id;
}

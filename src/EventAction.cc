#include "EventAction.hh"

#include "G4Event.hh"

#include <limits>

namespace {

G4ThreeVector NanPosition()
{
    const double nan = std::numeric_limits<double>::quiet_NaN();
    return G4ThreeVector(nan, nan, nan);
}

} // namespace

bool ScatterSummary::HasScatter() const
{
    return scatter_count_total > 0;
}

bool ScatterSummary::IsMultipleScatter() const
{
    return scatter_count_total >= 2;
}

void EventAction::BeginOfEventAction(const G4Event* event)
{
    ResetRecord(event != nullptr ? event->GetEventID() : -1);
}

void EventAction::EndOfEventAction(const G4Event*)
{
}

void EventAction::SetInitialEnergy(double energy_keV)
{
    record_.initial_energy_keV = energy_keV;
}

void EventAction::RecordComptonScatter(const G4ThreeVector& position)
{
    ++record_.scatter.compton_count;
    RecordScatter(position);
}

void EventAction::RecordRayleighScatter(const G4ThreeVector& position)
{
    ++record_.scatter.rayleigh_count;
    RecordScatter(position);
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

bool EventAction::IsMultipleScatter() const
{
    return record_.scatter.IsMultipleScatter();
}

const EventRecord& EventAction::GetRecord() const
{
    return record_;
}

void EventAction::ResetRecord(int eventId)
{
    record_ = EventRecord{};
    record_.event_id = eventId;
    record_.scatter.first_scatter_pos = NanPosition();
    record_.scatter.last_scatter_pos = NanPosition();
}

void EventAction::RecordScatter(const G4ThreeVector& position)
{
    auto& scatter = record_.scatter;
    if (!scatter.HasScatter()) {
        scatter.first_scatter_pos = position;
    }

    ++scatter.scatter_count_total;
    scatter.last_scatter_pos = position;
}

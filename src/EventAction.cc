#include "EventAction.hh"

#include "CsvWriter.hh"

#include "G4Event.hh"
#include "G4Exception.hh"
#include "G4PrimaryParticle.hh"
#include "G4PrimaryVertex.hh"
#include "G4SystemOfUnits.hh"

#include <limits>
#include <string>
#include <utility>

namespace {

G4ThreeVector NanPosition()
{
    const double nan = std::numeric_limits<double>::quiet_NaN();
    return G4ThreeVector(nan, nan, nan);
}

void ReportEventError(const std::string& message)
{
    G4Exception("EventAction", "MSSEvent001", FatalException, message.c_str());
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

EventAction::EventAction(std::shared_ptr<CsvWriter> csvWriter)
    : csvWriter_(std::move(csvWriter))
{
}

void EventAction::BeginOfEventAction(const G4Event* event)
{
    ResetRecord(event != nullptr ? event->GetEventID() : -1);

    if (event == nullptr) {
        ReportEventError("Cannot read initial primary state from a null event.");
    }

    const auto* vertex = event->GetPrimaryVertex(0);
    if (vertex == nullptr) {
        ReportEventError("Event has no primary vertex; initial primary state is unavailable.");
    }

    const auto* primary = vertex->GetPrimary(0);
    if (primary == nullptr) {
        ReportEventError("Primary vertex has no primary particle; initial primary state is unavailable.");
    }

    const G4ThreeVector momentum(primary->GetPx(), primary->GetPy(), primary->GetPz());
    if (momentum.mag2() == 0.0) {
        ReportEventError("Primary particle has zero momentum; initial direction is unavailable.");
    }

    record_.initial_energy_keV = primary->GetKineticEnergy() / keV;
    record_.initial_dir = momentum.unit();
}

void EventAction::EndOfEventAction(const G4Event*)
{
    if (record_.hit.detected && csvWriter_ != nullptr) {
        csvWriter_->WriteRow(record_);
    }
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

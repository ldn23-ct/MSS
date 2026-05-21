#include "EventAction.hh"

#include "G4Event.hh"

void EventAction::BeginOfEventAction(const G4Event* event)
{
    record_ = EventRecord{};
    if (event != nullptr) {
        record_.event_id = event->GetEventID();
    }
}

void EventAction::EndOfEventAction(const G4Event*) {}

const EventRecord& EventAction::CurrentRecord() const
{
    return record_;
}

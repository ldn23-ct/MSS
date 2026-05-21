#ifndef EVENT_ACTION_HH
#define EVENT_ACTION_HH

#include "EventRecord.hh"

#include "G4UserEventAction.hh"

class G4Event;

class EventAction : public G4UserEventAction {
  public:
    EventAction() = default;
    ~EventAction() override = default;

    void BeginOfEventAction(const G4Event* event) override;
    void EndOfEventAction(const G4Event* event) override;

    const EventRecord& CurrentRecord() const;

  private:
    EventRecord record_;
};

#endif

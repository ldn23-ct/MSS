#ifndef EVENT_ACTION_HH
#define EVENT_ACTION_HH

#include "EventRecord.hh"

#include "G4UserEventAction.hh"

#include <string>

class G4Event;

class EventAction : public G4UserEventAction {
  public:
    EventAction() = default;
    ~EventAction() override = default;

    void BeginOfEventAction(const G4Event* event) override;
    void EndOfEventAction(const G4Event* event) override;

    void RecordComptonScatter(const G4ThreeVector& pos, const std::string& region_id);
    void RecordRayleighScatter(const G4ThreeVector& pos, const std::string& region_id);
    void RecordDetectorHit(const DetectorHitRecord& hit);

    bool HasDetectorHit() const;
    const EventRecord& GetRecord() const;
    const EventRecord& CurrentRecord() const;

  private:
    void RecordScatter(const G4ThreeVector& pos, const std::string& region_id);

    EventRecord record_;
};

#endif

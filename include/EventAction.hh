#ifndef EVENT_ACTION_HH
#define EVENT_ACTION_HH

#include "EventRecord.hh"

#include "G4UserEventAction.hh"

#include <string>

class CsvWriter;
class G4Event;
class G4Track;
class G4VPhysicalVolume;
class RegionResolver;

class EventAction : public G4UserEventAction {
  public:
    explicit EventAction(CsvWriter* writer = nullptr);
    ~EventAction() override = default;

    void BeginOfEventAction(const G4Event* event) override;
    void EndOfEventAction(const G4Event* event) override;

    GammaTrackSummary& EnsureGammaTrackSummary(const G4Track& track,
                                               const G4VPhysicalVolume* sourceVolume,
                                               const RegionResolver* resolver);
    void RecordComptonScatter(int track_id, const G4ThreeVector& pos, const std::string& region_id);
    void RecordRayleighScatter(int track_id, const G4ThreeVector& pos, const std::string& region_id);
    void RecordDetectorHit(int track_id, const DetectorHitRecord& hit);

    bool HasDetectorHit(int track_id) const;
    const EventRecord& GetRecord() const;
    const EventRecord& CurrentRecord() const;

  private:
    void RecordScatter(GammaTrackSummary& summary, const G4ThreeVector& pos, const std::string& region_id);
    std::string ResolveSourceRegion(const G4VPhysicalVolume* sourceVolume, const RegionResolver* resolver) const;

    CsvWriter* writer_ = nullptr;
    EventRecord record_;
};

#endif

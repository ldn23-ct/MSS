#ifndef EVENT_ACTION_HH
#define EVENT_ACTION_HH

#include "G4ThreeVector.hh"
#include "G4UserEventAction.hh"

class G4Event;

struct ScatterSummary {
    int scatter_count_total = 0;
    int compton_count = 0;
    int rayleigh_count = 0;
    G4ThreeVector first_scatter_pos;
    G4ThreeVector last_scatter_pos;

    bool HasScatter() const;
    bool IsMultipleScatter() const;
};

struct DetectorHitRecord {
    bool detected = false;
    double det_x = 0.0;
    double det_y = 0.0;
    double det_z = -73.0;
    double det_energy_keV = 0.0;
    G4ThreeVector det_dir;
};

struct EventRecord {
    int event_id = -1;
    int track_id = 1;
    int parent_id = 0;
    double initial_energy_keV = 0.0;
    ScatterSummary scatter;
    DetectorHitRecord hit;
};

class EventAction : public G4UserEventAction {
  public:
    EventAction() = default;
    ~EventAction() override = default;

    void BeginOfEventAction(const G4Event* event) override;
    void EndOfEventAction(const G4Event* event) override;

    void SetInitialEnergy(double energy_keV);
    void RecordComptonScatter(const G4ThreeVector& position);
    void RecordRayleighScatter(const G4ThreeVector& position);
    void RecordDetectorHit(const DetectorHitRecord& hit);

    bool HasDetectorHit() const;
    bool IsMultipleScatter() const;
    const EventRecord& GetRecord() const;

  private:
    void ResetRecord(int eventId);
    void RecordScatter(const G4ThreeVector& position);

    EventRecord record_;
};

#endif

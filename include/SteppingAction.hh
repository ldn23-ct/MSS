#ifndef STEPPING_ACTION_HH
#define STEPPING_ACTION_HH

#include "VirtualDetectorPlane.hh"

#include "G4UserSteppingAction.hh"

class EventAction;
class G4Step;
class G4Track;
class RegionResolver;

class SteppingAction : public G4UserSteppingAction {
  public:
    SteppingAction(EventAction* eventAction,
                   const RegionResolver* regionResolver,
                   const DetectorPlaneActual& detectorPlane);
    ~SteppingAction() override = default;

    void UserSteppingAction(const G4Step* step) override;

  private:
    bool TryRecordDetectorCrossing(const G4Step& step, const G4Track& track);
    bool IsInsideDetectorBounds(double x_mm, double y_mm) const;

    EventAction* eventAction_ = nullptr;
    const RegionResolver* regionResolver_ = nullptr;
    DetectorPlaneActual detectorPlane_;
};

#endif

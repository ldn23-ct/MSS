#ifndef STEPPING_ACTION_HH
#define STEPPING_ACTION_HH

#include "DetectorConstruction.hh"

#include "G4UserSteppingAction.hh"

class EventAction;
class G4Step;

class SteppingAction : public G4UserSteppingAction {
  public:
    SteppingAction(EventAction* eventAction,
                   const DetectorPlaneConfig& detectorPlaneConfig);
    ~SteppingAction() override = default;

    void UserSteppingAction(const G4Step* step) override;

  private:
    EventAction* eventAction_ = nullptr;
    DetectorPlaneConfig detectorPlaneConfig_;
};

#endif

#ifndef STEPPING_ACTION_HH
#define STEPPING_ACTION_HH

#include "DetectorConstruction.hh"

#include "G4UserSteppingAction.hh"

#include <array>

class EventAction;
class G4Step;

class SteppingAction : public G4UserSteppingAction {
  public:
    SteppingAction(EventAction* eventAction,
                   const std::array<DetectorPlaneConfig, 2>& detectorPlaneConfigs);
    ~SteppingAction() override = default;

    void UserSteppingAction(const G4Step* step) override;

  private:
    EventAction* eventAction_ = nullptr;
    std::array<DetectorPlaneConfig, 2> detectorPlaneConfigs_;
};

#endif

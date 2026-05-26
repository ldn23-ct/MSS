#ifndef STEPPING_ACTION_HH
#define STEPPING_ACTION_HH

#include "G4UserSteppingAction.hh"

class EventAction;
class G4Step;
class RegionResolver;

class SteppingAction : public G4UserSteppingAction {
  public:
    SteppingAction(EventAction* eventAction, const RegionResolver* regionResolver);
    ~SteppingAction() override = default;

    void UserSteppingAction(const G4Step* step) override;

  private:
    EventAction* eventAction_ = nullptr;
    const RegionResolver* regionResolver_ = nullptr;
};

#endif

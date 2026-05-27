#ifndef ACTION_INITIALIZATION_HH
#define ACTION_INITIALIZATION_HH

#include "ScanPoseManager.hh"
#include "SimulationConfig.hh"
#include "VehicleROIConfig.hh"
#include "VirtualDetectorPlane.hh"

#include "G4VUserActionInitialization.hh"

class RegionResolver;

class ActionInitialization : public G4VUserActionInitialization {
  public:
    ActionInitialization() = default;
    explicit ActionInitialization(const SimulationConfig& config);
    ActionInitialization(const SimulationConfig& config, const ScanPose& pose);
    ActionInitialization(const SimulationConfig& config,
                         const ScanPose& pose,
                         const VehicleROIConfig& vehicleROI);
    ActionInitialization(const SimulationConfig& config,
                         const ScanPose& pose,
                         const VehicleROIConfig& vehicleROI,
                         const RegionResolver* regionResolver);
    ~ActionInitialization() override = default;

    void BuildForMaster() const override;
    void Build() const override;

  private:
    bool hasConfig_ = false;
    SimulationConfig config_;
    VehicleROIConfig vehicleROI_;
    ScanPose pose_;
    DetectorPlaneActual detectorPlane_;
    const RegionResolver* regionResolver_ = nullptr;
};

#endif

#ifndef POSE_RUN_CONTROLLER_HH
#define POSE_RUN_CONTROLLER_HH

#include "ScanPoseManager.hh"
#include "SimulationConfig.hh"
#include "VehicleROIConfig.hh"

#include <string>

class PoseRunController {
  public:
    PoseRunController() = default;

    void Execute(const SimulationConfig& config,
                 const VehicleROIConfig& vehicleROI,
                 const PoseList& poses) const;

  private:
    std::string BuildRunId(const SimulationConfig& config, const ScanPose& pose) const;
    void ValidateRunOutputDirectoriesAvailable(const SimulationConfig& config, const PoseList& poses) const;
    void RunPoseInChild(const SimulationConfig& config,
                        const VehicleROIConfig& vehicleROI,
                        const ScanPose& pose) const;
    void RunPose(const SimulationConfig& config,
                 const VehicleROIConfig& vehicleROI,
                 const ScanPose& pose) const;
};

#endif

#ifndef VISUALIZATION_CONTROLLER_HH
#define VISUALIZATION_CONTROLLER_HH

#include "ScanPoseManager.hh"
#include "SimulationConfig.hh"
#include "VehicleROIConfig.hh"

class VisualizationController {
  public:
    VisualizationController() = default;

    void Execute(const SimulationConfig& config,
                 const VehicleROIConfig& vehicleROI,
                 const PoseList& poses) const;
};

#endif

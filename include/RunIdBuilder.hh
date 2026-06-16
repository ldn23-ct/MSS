#ifndef RUN_ID_BUILDER_HH
#define RUN_ID_BUILDER_HH

#include "ScanPoseManager.hh"
#include "SimulationConfig.hh"

#include <string>

namespace mss {

std::string BuildRunId(const SimulationConfig& config, const ScanPose& pose);

}  // namespace mss

#endif

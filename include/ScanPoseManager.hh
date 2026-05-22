#ifndef SCAN_POSE_MANAGER_HH
#define SCAN_POSE_MANAGER_HH

#include "SimulationConfig.hh"

#include <string>
#include <vector>

struct ScanPose {
    int pose_index = 0;
    int head_offset_x_mm = 0;
    int head_offset_y_mm = 0;
    long random_seed = 0;
    std::string pose_id;
};

using PoseList = std::vector<ScanPose>;

class ScanPoseManager {
  public:
    ScanPoseManager() = default;

    PoseList Generate(const SimulationConfig& config) const;
    std::string BuildPoseId(int x_mm, int y_mm) const;
    long SeedForPose(long base_seed, int pose_index) const;

  private:
    ScanPose BuildPose(int poseIndex, int xMm, int yMm, long baseSeed) const;
};

#endif

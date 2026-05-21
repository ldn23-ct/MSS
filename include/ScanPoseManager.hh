#ifndef SCAN_POSE_MANAGER_HH
#define SCAN_POSE_MANAGER_HH

#include <string>
#include <vector>

struct ScanPose {
    std::string pose_id;
    int head_offset_x_mm = 0;
    int head_offset_y_mm = 0;
};

using PoseList = std::vector<ScanPose>;

class ScanPoseManager {
  public:
    ScanPoseManager() = default;
};

#endif

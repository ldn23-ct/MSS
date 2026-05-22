#include "ScanPoseManager.hh"

#include <cstdlib>
#include <limits>
#include <stdexcept>

namespace {

std::string EncodeOffset(int value)
{
    if (value == 0) {
        return "0";
    }
    if (value > 0) {
        return std::to_string(value);
    }

    long long widened = static_cast<long long>(value);
    return "m" + std::to_string(std::llabs(widened));
}

}  // namespace

PoseList ScanPoseManager::Generate(const SimulationConfig& config) const
{
    PoseList poses;

    if (config.pose.mode == "list") {
        const auto& xs = config.pose.list_head_offset_x_mm;
        const auto& ys = config.pose.list_head_offset_y_mm;
        if (xs.size() != ys.size()) {
            throw std::runtime_error(
                "pose.list.head_offset_x_mm and pose.list.head_offset_y_mm must have the same length");
        }
        if (xs.empty()) {
            throw std::runtime_error("pose.list head_offset arrays must not be empty");
        }

        poses.reserve(xs.size());
        for (std::size_t i = 0; i < xs.size(); ++i) {
            poses.push_back(BuildPose(static_cast<int>(i), xs[i], ys[i], config.run.random_seed));
        }
        return poses;
    }

    if (config.pose.mode == "grid") {
        const auto& xs = config.pose.grid_x_offsets_mm;
        const auto& ys = config.pose.grid_y_offsets_mm;
        if (xs.empty()) {
            throw std::runtime_error("pose.grid.x_offsets_mm must not be empty in grid mode");
        }
        if (ys.empty()) {
            throw std::runtime_error("pose.grid.y_offsets_mm must not be empty in grid mode");
        }

        poses.reserve(xs.size() * ys.size());
        int poseIndex = 0;
        for (const int x : xs) {
            for (const int y : ys) {
                poses.push_back(BuildPose(poseIndex, x, y, config.run.random_seed));
                ++poseIndex;
            }
        }
        return poses;
    }

    throw std::runtime_error("pose.mode must be list or grid");
}

std::string ScanPoseManager::BuildPoseId(int x_mm, int y_mm) const
{
    return "pose_x" + EncodeOffset(x_mm) + "_y" + EncodeOffset(y_mm);
}

long ScanPoseManager::SeedForPose(long base_seed, int pose_index) const
{
    if (pose_index < 0) {
        throw std::runtime_error("pose_index must be non-negative");
    }
    if (base_seed > std::numeric_limits<long>::max() - pose_index) {
        throw std::runtime_error("pose random_seed overflows long");
    }
    return base_seed + pose_index;
}

ScanPose ScanPoseManager::BuildPose(int poseIndex, int xMm, int yMm, long baseSeed) const
{
    ScanPose pose;
    pose.pose_index = poseIndex;
    pose.head_offset_x_mm = xMm;
    pose.head_offset_y_mm = yMm;
    pose.random_seed = SeedForPose(baseSeed, poseIndex);
    pose.pose_id = BuildPoseId(xMm, yMm);
    return pose;
}

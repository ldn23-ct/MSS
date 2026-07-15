#include "ScanPoseManager.hh"

#include <cstdlib>
#include <cmath>
#include <iomanip>
#include <limits>
#include <sstream>
#include <stdexcept>

namespace {

long long OffsetMicrometres(double value)
{
    if (!std::isfinite(value)) {
        throw std::runtime_error("pose offset must be finite");
    }
    constexpr long double scale = 1000000.0L;
    const long double scaled = static_cast<long double>(value) * scale;
    if (scaled < static_cast<long double>(std::numeric_limits<long long>::min())
        || scaled > static_cast<long double>(std::numeric_limits<long long>::max())) {
        throw std::runtime_error("pose offset is outside the supported range");
    }
    const auto rounded = static_cast<long long>(std::llround(scaled));
    if (std::abs(scaled - static_cast<long double>(rounded)) > 1.0e-6L) {
        throw std::runtime_error("pose offset must contain at most six decimal places");
    }
    return rounded;
}

std::string EncodeOffset(double value)
{
    const long long micrometres = OffsetMicrometres(value);
    if (micrometres == 0) {
        return "0";
    }

    const bool negative = micrometres < 0;
    const unsigned long long magnitude = negative
                                             ? static_cast<unsigned long long>(-(micrometres + 1)) + 1ULL
                                             : static_cast<unsigned long long>(micrometres);
    const auto whole = magnitude / 1000000ULL;
    const auto fraction = magnitude % 1000000ULL;

    std::string encoded = negative ? "m" : "";
    encoded += std::to_string(whole);
    if (fraction != 0) {
        std::ostringstream stream;
        stream << std::setw(6) << std::setfill('0') << fraction;
        std::string fractionalText = stream.str();
        while (!fractionalText.empty() && fractionalText.back() == '0') {
            fractionalText.pop_back();
        }
        encoded += "p" + fractionalText;
    }
    return encoded;
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
        for (const double x : xs) {
            for (const double y : ys) {
                poses.push_back(BuildPose(poseIndex, x, y, config.run.random_seed));
                ++poseIndex;
            }
        }
        return poses;
    }

    throw std::runtime_error("pose.mode must be list or grid");
}

std::string ScanPoseManager::BuildPoseId(double x_mm, double y_mm) const
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

ScanPose ScanPoseManager::BuildPose(int poseIndex, double xMm, double yMm, long baseSeed) const
{
    ScanPose pose;
    pose.pose_index = poseIndex;
    pose.head_offset_x_mm = xMm;
    pose.head_offset_y_mm = yMm;
    pose.random_seed = SeedForPose(baseSeed, poseIndex);
    pose.pose_id = BuildPoseId(xMm, yMm);
    return pose;
}

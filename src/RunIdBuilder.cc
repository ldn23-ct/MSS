#include "RunIdBuilder.hh"

#include <cctype>
#include <cmath>
#include <iomanip>
#include <sstream>
#include <string>

namespace {

std::string SanitizeToken(const std::string& value)
{
    std::string sanitized;
    sanitized.reserve(value.size());
    for (const char ch : value) {
        const auto uch = static_cast<unsigned char>(ch);
        if (std::isalnum(uch) || ch == '_') {
            sanitized.push_back(ch);
        } else if (ch == '-') {
            sanitized.push_back('m');
        } else if (ch == '.') {
            sanitized.push_back('p');
        } else {
            sanitized.push_back('_');
        }
    }
    return sanitized.empty() ? "none" : sanitized;
}

std::string FormatEnergyValue(double value)
{
    if (!std::isfinite(value)) {
        return "invalid";
    }

    std::ostringstream stream;
    stream << std::setprecision(12) << value;
    std::string text = stream.str();
    if (text.find_first_of("eE") == std::string::npos && text.find('.') != std::string::npos) {
        while (!text.empty() && text.back() == '0') {
            text.pop_back();
        }
        if (!text.empty() && text.back() == '.') {
            text.pop_back();
        }
    }
    return SanitizeToken(text);
}

std::string SystemId(const SimulationConfig& config)
{
    return config.collimator.enable ? "collimated" : "open";
}

std::string ModelState(const SimulationConfig& config)
{
    if (config.vehicle.model_type == "normal") {
        return "normal";
    }

    const std::string target = config.vehicle.selected_target_component
                                   ? SanitizeToken(*config.vehicle.selected_target_component)
                                   : "unknown_target";
    return "abnormal_" + target + "_" + SanitizeToken(config.vehicle.abnormal_material);
}

std::string EnergyId(const SimulationConfig& config)
{
    if (config.source.energy_mode == "mono") {
        return "E" + FormatEnergyValue(config.source.mono_energy_keV) + "keV";
    }
    return "spectrum";
}

}  // namespace

namespace mss {

std::string BuildRunId(const SimulationConfig& config, const ScanPose& pose)
{
    return pose.pose_id + "_" + SystemId(config) + "_" + ModelState(config) + "_"
        + EnergyId(config) + "_seed" + std::to_string(pose.random_seed);
}

}  // namespace mss

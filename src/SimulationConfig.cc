#include "SimulationConfig.hh"

#include <filesystem>
#include <stdexcept>

void SimulationConfig::ValidateConfigPathOnly() const
{
    if (configFilePath.empty()) {
        throw std::runtime_error("config path is empty");
    }

    const std::filesystem::path path(configFilePath);
    if (!std::filesystem::exists(path)) {
        throw std::runtime_error("config file does not exist: " + configFilePath);
    }
    if (!std::filesystem::is_regular_file(path)) {
        throw std::runtime_error("config path is not a regular file: " + configFilePath);
    }
}

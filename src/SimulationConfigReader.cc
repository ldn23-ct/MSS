#include "SimulationConfigReader.hh"

SimulationConfig SimulationConfigReader::ReadPathOnly(const std::string& configFilePath) const
{
    SimulationConfig config;
    config.configFilePath = configFilePath;
    config.ValidateConfigPathOnly();
    return config;
}

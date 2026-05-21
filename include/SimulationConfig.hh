#ifndef SIMULATION_CONFIG_HH
#define SIMULATION_CONFIG_HH

#include <string>

struct SimulationConfig {
    std::string configFilePath;

    void ValidateConfigPathOnly() const;
};

#endif

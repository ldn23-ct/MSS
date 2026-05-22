#ifndef SIMULATION_CONFIG_READER_HH
#define SIMULATION_CONFIG_READER_HH

#include "SimulationConfig.hh"

#include <string>

class SimulationConfigReader {
  public:
    SimulationConfig Read(const std::string& configFilePath) const;
    SimulationConfig ReadPathOnly(const std::string& configFilePath) const;
};

#endif

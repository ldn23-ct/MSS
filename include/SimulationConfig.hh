#ifndef SIMULATION_CONFIG_HH
#define SIMULATION_CONFIG_HH

#include <optional>
#include <string>

struct SimulationConfig {
    std::string collimatorProfileFile = "data/collimator_profiles.csv";
    std::string collimatorProfileId = "P001";
    bool enableCollimator = true;
    bool enableAirDefect = true;

    std::string energyMode = "mono";
    double monoEnergy_keV = 160.0;
    std::string spectrumFile = "data/spectrum.csv";

    long randomSeed = 12345;
    int numberOfThreads = 1;

    std::string outputDirectory = "results";
    std::optional<bool> debugOutputOverride = std::nullopt;

    void Validate() const;
    bool ResolveDebugOutput() const;
};

#endif

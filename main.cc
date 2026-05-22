#include "SimulationConfig.hh"
#include "SimulationConfigReader.hh"

#include <exception>
#include <iostream>
#include <string>

namespace {

struct CliOptions {
    std::string configPath;
};

void PrintUsage(std::ostream& os)
{
    os << "Usage:\n"
       << "  MSS --config <simulation_config_v2.yaml>\n"
       << "  MSS <simulation_config_v2.yaml>\n";
}

bool StartsWithDash(const std::string& value)
{
    return !value.empty() && value.front() == 45;
}

CliOptions ParseArgs(int argc, char** argv)
{
    std::string configFromFlag;
    std::string configFromPosition;

    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--config") {
            if (i + 1 >= argc || StartsWithDash(argv[i + 1])) {
                throw std::runtime_error("missing value after --config");
            }
            configFromFlag = argv[++i];
            continue;
        }
        if (StartsWithDash(arg)) {
            throw std::runtime_error("unknown option: " + arg);
        }
        if (!configFromPosition.empty()) {
            throw std::runtime_error("multiple positional config paths are not allowed");
        }
        configFromPosition = arg;
    }

    CliOptions options;
    options.configPath = configFromFlag.empty() ? configFromPosition : configFromFlag;
    if (options.configPath.empty()) {
        throw std::runtime_error("no YAML config path specified");
    }
    return options;
}

void PrintConfigSummary(const SimulationConfig& config)
{
    std::cout << "MSS M1 configuration loaded.\n"
              << "Config path: " << config.configFilePath << "\n"
              << "schema_version: " << config.schema_version << "\n"
              << "run.number_of_threads: " << config.run.number_of_threads << "\n"
              << "run.n_primary_per_pose: " << config.run.n_primary_per_pose << "\n"
              << "vehicle.model_type: " << config.vehicle.model_type << "\n"
              << "vehicle.geometry_file: " << config.vehicle.geometry_file << "\n"
              << "pose.mode: " << config.pose.mode << "\n"
              << "source.energy_mode: " << config.source.energy_mode << "\n"
              << "source.incident_theta_deg: " << config.source.incident_theta_deg << "\n"
              << "detector.detector_z_zero_mm: " << config.detector.detector_z_zero_mm << "\n"
              << "detector.detector_x_range_zero_mm: ["
              << config.detector.detector_x_range_zero_mm[0] << ", "
              << config.detector.detector_x_range_zero_mm[1] << "]\n"
              << "detector.detector_y_range_zero_mm: ["
              << config.detector.detector_y_range_zero_mm[0] << ", "
              << config.detector.detector_y_range_zero_mm[1] << "]\n"
              << "output.output_directory: " << config.output.output_directory << "\n"
              << "Geant4 simulation is deferred beyond M1.\n";
}

}  // namespace

int main(int argc, char** argv)
{
    try {
        const auto options = ParseArgs(argc, argv);
        SimulationConfigReader reader;
        const auto config = reader.Read(options.configPath);
        PrintConfigSummary(config);
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "MSS error: " << error.what() << "\n\n";
        PrintUsage(std::cerr);
        return 2;
    }
}

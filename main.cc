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
    return !value.empty() && value.front() == '-';
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

}  // namespace

int main(int argc, char** argv)
{
    try {
        const auto options = ParseArgs(argc, argv);
        SimulationConfigReader reader;
        const auto config = reader.ReadPathOnly(options.configPath);

        std::cout << "MSS M0 skeleton initialized.\n"
                  << "Config path: " << config.configFilePath << '\n'
                  << "YAML parsing and Geant4 simulation are deferred to later milestones.\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "MSS error: " << error.what() << "\n\n";
        PrintUsage(std::cerr);
        return 2;
    }
}

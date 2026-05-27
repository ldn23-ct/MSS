#include "ActionInitialization.hh"
#include "DetectorConstruction.hh"
#include "PhysicsList.hh"
#include "SimulationConfig.hh"
#include "ScanPoseManager.hh"
#include "SimulationConfigReader.hh"
#include "VehicleROIConfigReader.hh"

#include "G4RunManagerFactory.hh"
#include "G4RunManager.hh"
#include "Randomize.hh"

#include <algorithm>
#include <exception>
#include <filesystem>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>

namespace {

namespace fs = std::filesystem;

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
    std::cout << "MSS configuration loaded.\n"
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
              << "output.output_directory: " << config.output.output_directory << "\n";
}


void PrintPoseSummary(const PoseList& poses)
{
    std::cout << "ScanPoseManager pose list generated.\n"
              << "pose_count: " << poses.size() << "\n";
    for (const auto& pose : poses) {
        std::cout << "pose[" << pose.pose_index << "]: "
                  << pose.pose_id
                  << " head_offset_x_mm=" << pose.head_offset_x_mm
                  << " head_offset_y_mm=" << pose.head_offset_y_mm
                  << " random_seed=" << pose.random_seed << "\n";
    }
}

void PrintVehicleROISummary(const VehicleROIConfig& vehicleROI)
{
    const auto insertCount = std::count_if(
        vehicleROI.components.begin(),
        vehicleROI.components.end(),
        [](const BoxComponentConfig& component) { return component.is_insert; });

    std::cout << "VehicleROI M2 configuration loaded.\n"
              << "vehicle.geometry_file: " << vehicleROI.geometry_file << "\n"
              << "vehicle_model_id: " << vehicleROI.vehicle_model_id << "\n"
              << "root component: " << vehicleROI.root_roi.name << "\n"
              << "component_count: " << vehicleROI.components.size() << "\n"
              << "insert_count: " << insertCount << "\n"
              << "region_count: " << vehicleROI.detailed_region_ids.size() << "\n"
              << "recommended_target_count: " << vehicleROI.recommended_target_components.size() << "\n";
}

std::string BuildRunId(const SimulationConfig& config, const ScanPose& pose)
{
    return pose.pose_id + "_" + config.vehicle.model_type + "_seed" + std::to_string(pose.random_seed);
}

void ValidateRunOutputDirectoryAvailable(const SimulationConfig& config, const ScanPose& pose)
{
    const fs::path runDir = fs::path(config.output.output_directory) / BuildRunId(config, pose);
    if (!fs::exists(runDir)) {
        return;
    }
    if (!fs::is_directory(runDir)) {
        throw std::runtime_error("run output path exists but is not a directory: " + runDir.string());
    }
    if (fs::directory_iterator(runDir) != fs::directory_iterator()) {
        throw std::runtime_error("run output directory already exists and is non-empty: " + runDir.string());
    }
}

void RunFirstPose(const SimulationConfig& config, const VehicleROIConfig& vehicleROI, const PoseList& poses)
{
    if (poses.empty()) {
        throw std::runtime_error("no scan poses were generated");
    }
    if (config.run.number_of_threads != 1) {
        throw std::runtime_error("M13 run execution supports single-thread configs only; set run.number_of_threads to 1");
    }

    const ScanPose& pose = poses.front();
    ValidateRunOutputDirectoryAvailable(config, pose);
    CLHEP::HepRandom::setTheSeed(pose.random_seed);

    auto* detectorConstruction = new DetectorConstruction(config, vehicleROI);
    std::unique_ptr<G4RunManager> runManager(
        G4RunManagerFactory::CreateRunManager(G4RunManagerType::Default, config.run.number_of_threads));
    runManager->SetUserInitialization(detectorConstruction);
    runManager->SetUserInitialization(new PhysicsList());
    runManager->SetUserInitialization(new ActionInitialization(
        config,
        pose,
        vehicleROI,
        &detectorConstruction->GetRegionResolver()));

    runManager->Initialize();
    runManager->BeamOn(static_cast<G4int>(config.run.n_primary_per_pose));

    std::cout << "M14 single-pose run completed: " << pose.pose_id << "\n";
}

}  // namespace

int main(int argc, char** argv)
{
    try {
        const auto options = ParseArgs(argc, argv);
        SimulationConfigReader reader;
        const auto config = reader.Read(options.configPath);
        PrintConfigSummary(config);

        ScanPoseManager poseManager;
        const auto poses = poseManager.Generate(config);
        PrintPoseSummary(poses);

        VehicleROIConfigReader vehicleReader;
        const auto vehicleROI = vehicleReader.Read(config.vehicle);
        PrintVehicleROISummary(vehicleROI);

        RunFirstPose(config, vehicleROI, poses);
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "MSS error: " << error.what() << "\n\n";
        PrintUsage(std::cerr);
        return 2;
    }
}

#include "PoseRunController.hh"

#include "ActionInitialization.hh"
#include "DetectorConstruction.hh"
#include "PhysicsList.hh"
#include "RunIdBuilder.hh"

#include "G4RunManager.hh"
#include "G4RunManagerFactory.hh"
#include "Randomize.hh"

#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>

#include <sys/wait.h>
#include <unistd.h>

namespace fs = std::filesystem;

void PoseRunController::Execute(const SimulationConfig& config,
                                const VehicleROIConfig& vehicleROI,
                                const PoseList& poses) const
{
    if (poses.empty()) {
        throw std::runtime_error("no scan poses were generated");
    }

    ValidateRunOutputDirectoriesAvailable(config, poses);

    std::cout << "PoseRunController starting pose runs: " << poses.size() << "\n";
    for (const auto& pose : poses) {
        if (poses.size() == 1) {
            RunPose(config, vehicleROI, pose);
        } else {
            RunPoseInChild(config, vehicleROI, pose);
        }
    }
    std::cout << "PoseRunController completed pose runs: " << poses.size() << "\n";
}

std::string PoseRunController::BuildRunId(const SimulationConfig& config, const ScanPose& pose) const
{
    return mss::BuildRunId(config, pose);
}

void PoseRunController::ValidateRunOutputDirectoriesAvailable(const SimulationConfig& config,
                                                              const PoseList& poses) const
{
    std::set<std::string> runIds;
    for (const auto& pose : poses) {
        const std::string runId = BuildRunId(config, pose);
        if (!runIds.insert(runId).second) {
            throw std::runtime_error("duplicate run_id generated for pose runs: " + runId);
        }

        const fs::path runDir = fs::path(config.output.output_directory) / runId;
        if (!fs::exists(runDir)) {
            continue;
        }
        if (!fs::is_directory(runDir)) {
            throw std::runtime_error("run output path exists but is not a directory: " + runDir.string());
        }
        if (config.output.existing_run_policy == "fail"
            && fs::directory_iterator(runDir) != fs::directory_iterator()) {
            throw std::runtime_error("run output directory already exists and is non-empty: " + runDir.string());
        }
    }
}

void PoseRunController::RunPoseInChild(const SimulationConfig& config,
                                       const VehicleROIConfig& vehicleROI,
                                       const ScanPose& pose) const
{
    std::cout.flush();
    std::cerr.flush();

    const pid_t pid = fork();
    if (pid < 0) {
        throw std::runtime_error("failed to fork pose run process for " + pose.pose_id);
    }

    if (pid == 0) {
        try {
            RunPose(config, vehicleROI, pose);
            std::cout.flush();
            std::cerr.flush();
            _exit(EXIT_SUCCESS);
        } catch (const std::exception& error) {
            std::cerr << "MSS child pose run error for " << pose.pose_id << ": " << error.what() << "\n";
            std::cout.flush();
            std::cerr.flush();
            _exit(EXIT_FAILURE);
        } catch (...) {
            std::cerr << "MSS child pose run error for " << pose.pose_id << ": unknown error\n";
            std::cout.flush();
            std::cerr.flush();
            _exit(EXIT_FAILURE);
        }
    }

    int status = 0;
    if (waitpid(pid, &status, 0) < 0) {
        throw std::runtime_error("failed to wait for pose run process: " + pose.pose_id);
    }
    if (WIFEXITED(status) && WEXITSTATUS(status) == EXIT_SUCCESS) {
        return;
    }
    if (WIFSIGNALED(status)) {
        throw std::runtime_error(
            "pose run process terminated by signal " + std::to_string(WTERMSIG(status)) + ": " + pose.pose_id);
    }
    if (WIFEXITED(status)) {
        throw std::runtime_error(
            "pose run process failed with exit code " + std::to_string(WEXITSTATUS(status)) + ": " + pose.pose_id);
    }
    throw std::runtime_error("pose run process failed: " + pose.pose_id);
}

void PoseRunController::RunPose(const SimulationConfig& config,
                                const VehicleROIConfig& vehicleROI,
                                const ScanPose& pose) const
{
    std::cout << "Running pose " << pose.pose_index << ": " << pose.pose_id
              << " seed=" << pose.random_seed << "\n";

    CLHEP::HepRandom::setTheSeed(pose.random_seed);

    auto* detectorConstruction = new DetectorConstruction(config, vehicleROI, pose);
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
}

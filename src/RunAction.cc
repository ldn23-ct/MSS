#include "RunAction.hh"

#include "CsvWriter.hh"
#include "SimulationConfig.hh"

#ifdef G4MULTITHREADED
#include "G4MTRunManager.hh"
#include "G4Threading.hh"
#endif
#include "G4Exception.hh"
#include "G4RunManager.hh"
#include "Randomize.hh"

#include <cmath>
#include <filesystem>
#include <iomanip>
#include <sstream>
#include <string>
#include <utility>

namespace {

bool IsConfigOwnerThread()
{
#ifdef G4MULTITHREADED
    return G4Threading::IsMasterThread();
#else
    return true;
#endif
}

void ReportRunError(const std::string& message)
{
    G4Exception("RunAction", "MSSRun001", FatalException, message.c_str());
}

std::string FormatEnergyForFileName(double energy_keV)
{
    if (!std::isfinite(energy_keV) || energy_keV <= 0.0) {
        ReportRunError("monoEnergy must be positive and finite.");
    }

    std::ostringstream stream;
    stream << std::setprecision(12) << energy_keV;
    return stream.str();
}

std::filesystem::path BuildOutputFilePath(const SimulationConfig& config,
                                          bool debugOutput)
{
    std::ostringstream fileName;
    fileName << "hits_profile_" << config.collimatorProfileId << '_';
    if (config.energyMode == "mono") {
        fileName << "mono_" << FormatEnergyForFileName(config.monoEnergy_keV)
                 << "keV_seed" << config.randomSeed;
    } else if (config.energyMode == "spectrum") {
        fileName << "spectrum_seed" << config.randomSeed;
    } else {
        ReportRunError("energyMode must be either 'mono' or 'spectrum'.");
    }

    if (debugOutput) {
        fileName << "_debug";
    }
    fileName << ".csv";

    return std::filesystem::path(config.outputDirectory) / fileName.str();
}

void EnsureOutputDirectory(const std::string& outputDirectory)
{
    try {
        const std::filesystem::path directory(outputDirectory);
        if (std::filesystem::exists(directory)) {
            if (!std::filesystem::is_directory(directory)) {
                ReportRunError("Output path '" + outputDirectory
                               + "' exists but is not a directory.");
            }
            return;
        }

        if (!std::filesystem::create_directories(directory)) {
            ReportRunError("Failed to create output directory '"
                           + outputDirectory + "'.");
        }
    } catch (const std::filesystem::filesystem_error& error) {
        ReportRunError("Failed to prepare output directory '" + outputDirectory
                       + "': " + error.what());
    }
}

} // namespace

RunAction::RunAction(std::shared_ptr<SimulationConfig> config,
                     std::shared_ptr<CsvWriter> csvWriter)
    : config_(std::move(config)),
      csvWriter_(std::move(csvWriter))
{
}

void RunAction::BeginOfRunAction(const G4Run*)
{
    if (config_ != nullptr && IsConfigOwnerThread()) {
        config_->numberOfThreads = GetEffectiveNumberOfThreads();
        config_->Validate();

        if (config_->numberOfThreads > 1) {
            ReportRunError("Milestone 8 supports only single-thread CSV output; "
                           "multi-thread temporary CSV and merge are deferred "
                           "to Milestone 9.");
        }

        G4Random::setTheSeed(config_->randomSeed);

        const bool debugOutput = config_->ResolveDebugOutput();
        EnsureOutputDirectory(config_->outputDirectory);

        if (csvWriter_ == nullptr) {
            ReportRunError("CsvWriter is not available.");
        }

        const auto outputPath = BuildOutputFilePath(*config_, debugOutput);
        csvWriter_->Open(outputPath.string(), debugOutput);
    }
}

void RunAction::EndOfRunAction(const G4Run*)
{
    if (csvWriter_ != nullptr && IsConfigOwnerThread()) {
        csvWriter_->Close();
    }
}

int RunAction::GetEffectiveNumberOfThreads() const
{
#ifdef G4MULTITHREADED
    auto* runManager = G4RunManager::GetRunManager();
    auto* mtRunManager = dynamic_cast<G4MTRunManager*>(runManager);
    if (mtRunManager != nullptr && mtRunManager->GetNumberOfThreads() > 0) {
        return mtRunManager->GetNumberOfThreads();
    }

    if (runManager != nullptr) {
        return 1;
    }
#else
    if (G4RunManager::GetRunManager() != nullptr) {
        return 1;
    }
#endif

    if (config_ != nullptr && config_->numberOfThreads > 0) {
        return config_->numberOfThreads;
    }

    return 1;
}

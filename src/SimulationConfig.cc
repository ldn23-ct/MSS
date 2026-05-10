#include "SimulationConfig.hh"

#include "G4Exception.hh"

#include <cmath>
#include <string>

namespace {

void ReportConfigError(const std::string& message)
{
    G4Exception("SimulationConfig",
                "MSSConfig001",
                FatalException,
                message.c_str());
}

} // namespace

void SimulationConfig::Validate() const
{
    if (enableCollimator && collimatorProfileFile.empty()) {
        ReportConfigError("collimatorProfileFile must not be empty.");
    }

    if (enableCollimator && collimatorProfileId.empty()) {
        ReportConfigError("collimatorProfileId must not be empty.");
    }

    if (energyMode != "mono" && energyMode != "spectrum") {
        ReportConfigError("energyMode must be either 'mono' or 'spectrum'.");
    }

    if (!std::isfinite(monoEnergy_keV) || monoEnergy_keV <= 0.0) {
        ReportConfigError("monoEnergy must be positive and finite.");
    }

    if (energyMode == "spectrum" && spectrumFile.empty()) {
        ReportConfigError("spectrumFile must not be empty in spectrum mode.");
    }

    if (numberOfThreads < 1) {
        ReportConfigError("numberOfThreads must be at least 1.");
    }

    if (outputDirectory.empty()) {
        ReportConfigError("outputDirectory must not be empty.");
    }
}

bool SimulationConfig::ResolveDebugOutput() const
{
    if (debugOutputOverride.has_value()) {
        return *debugOutputOverride;
    }

    return numberOfThreads <= 1;
}

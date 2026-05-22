#include "SourceModel.hh"

#include "Randomize.hh"

#include <cmath>
#include <stdexcept>

namespace {

constexpr double kPi = 3.141592653589793238462643383279502884;

bool IsFinite(double value)
{
    return std::isfinite(value);
}

}  // namespace

SourceModel::SourceModel(const SourceConfig& sourceConfig, const ScanPose& pose)
    : sourceConfig_(sourceConfig),
      pose_(pose),
      sourcePositionActualMm_(
          sourceConfig.source_pos_zero_mm[0] + pose.head_offset_x_mm,
          sourceConfig.source_pos_zero_mm[1] + pose.head_offset_y_mm,
          sourceConfig.source_pos_zero_mm[2])
{
    ValidateSourceConfig();

    const double thetaRad = sourceConfig_.incident_theta_deg * kPi / 180.0;
    incidentDirection_ = G4ThreeVector(std::cos(thetaRad), 0.0, std::sin(thetaRad)).unit();

    if (sourceConfig_.energy_mode == "spectrum") {
        spectrumSampler_.Load(sourceConfig_.spectrum_file);
    }
}

PrimarySample SourceModel::SamplePrimary() const
{
    PrimarySample sample;
    sample.position_mm = SamplePositionMm();
    sample.direction = incidentDirection_;
    sample.energy_keV = SampleEnergyKeV();
    return sample;
}

G4ThreeVector SourceModel::SamplePositionMm() const
{
    const double thetaRad = sourceConfig_.incident_theta_deg * kPi / 180.0;
    const G4ThreeVector u(0.0, 1.0, 0.0);
    const G4ThreeVector v(-std::sin(thetaRad), 0.0, std::cos(thetaRad));

    const double radiusMm = FocalSpotRadiusMm();
    const double r = radiusMm * std::sqrt(G4UniformRand());
    const double phi = 2.0 * kPi * G4UniformRand();

    return sourcePositionActualMm_ + (r * std::cos(phi)) * u + (r * std::sin(phi)) * v;
}

double SourceModel::SampleEnergyKeV() const
{
    if (sourceConfig_.energy_mode == "mono") {
        return sourceConfig_.mono_energy_keV;
    }
    if (sourceConfig_.energy_mode == "spectrum") {
        return spectrumSampler_.SampleEnergyKeV();
    }
    throw std::runtime_error("source.energy_mode must be mono or spectrum");
}

const G4ThreeVector& SourceModel::SourcePositionActualMm() const
{
    return sourcePositionActualMm_;
}

const G4ThreeVector& SourceModel::IncidentDirection() const
{
    return incidentDirection_;
}

double SourceModel::FocalSpotRadiusMm() const
{
    return sourceConfig_.focal_spot_diameter_mm * 0.5;
}

void SourceModel::ValidateSourceConfig() const
{
    if (sourceConfig_.particle != "gamma") {
        throw std::runtime_error("source.particle must be gamma");
    }
    if (sourceConfig_.energy_mode != "mono" && sourceConfig_.energy_mode != "spectrum") {
        throw std::runtime_error("source.energy_mode must be mono or spectrum");
    }
    if (!IsFinite(sourceConfig_.mono_energy_keV) || sourceConfig_.mono_energy_keV <= 0.0) {
        throw std::runtime_error("source.mono_energy_keV must be finite and > 0");
    }
    if (sourceConfig_.energy_mode == "spectrum" && sourceConfig_.spectrum_file.empty()) {
        throw std::runtime_error("source.spectrum_file must be non-empty for spectrum energy_mode");
    }
    for (double value : sourceConfig_.source_pos_zero_mm) {
        if (!IsFinite(value)) {
            throw std::runtime_error("source.source_pos_zero_mm must contain only finite values");
        }
    }
    if (!IsFinite(sourceConfig_.incident_theta_deg)
        || sourceConfig_.incident_theta_deg <= 0.0
        || sourceConfig_.incident_theta_deg > 90.0) {
        throw std::runtime_error("source.incident_theta_deg must satisfy 0 < theta <= 90");
    }
    if (!IsFinite(sourceConfig_.focal_spot_diameter_mm) || sourceConfig_.focal_spot_diameter_mm <= 0.0) {
        throw std::runtime_error("source.focal_spot_diameter_mm must be finite and > 0");
    }
}

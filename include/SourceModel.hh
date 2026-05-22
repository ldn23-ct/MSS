#ifndef SOURCE_MODEL_HH
#define SOURCE_MODEL_HH

#include "ScanPoseManager.hh"
#include "SimulationConfig.hh"
#include "SpectrumSampler.hh"

#include "G4ThreeVector.hh"

struct PrimarySample {
    G4ThreeVector position_mm;
    G4ThreeVector direction;
    double energy_keV = 0.0;
};

class SourceModel {
  public:
    SourceModel(const SourceConfig& sourceConfig, const ScanPose& pose);

    PrimarySample SamplePrimary() const;
    G4ThreeVector SamplePositionMm() const;
    double SampleEnergyKeV() const;

    const G4ThreeVector& SourcePositionActualMm() const;
    const G4ThreeVector& IncidentDirection() const;
    double FocalSpotRadiusMm() const;

  private:
    void ValidateSourceConfig() const;

    SourceConfig sourceConfig_;
    ScanPose pose_;
    G4ThreeVector sourcePositionActualMm_;
    G4ThreeVector incidentDirection_;
    SpectrumSampler spectrumSampler_;
};

#endif

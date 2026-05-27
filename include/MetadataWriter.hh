#ifndef METADATA_WRITER_HH
#define METADATA_WRITER_HH

#include "ScanPoseManager.hh"
#include "SimulationConfig.hh"
#include "VehicleROIConfig.hh"

#include <string>

class MetadataWriter {
  public:
    MetadataWriter() = default;

    void Write(const std::string& filePath,
               const SimulationConfig& config,
               const VehicleROIConfig& vehicleROI,
               const ScanPose& pose,
               const std::string& runId,
               const std::string& outputCsvName) const;
};

#endif

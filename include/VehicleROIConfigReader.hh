#ifndef VEHICLE_ROI_CONFIG_READER_HH
#define VEHICLE_ROI_CONFIG_READER_HH

#include "VehicleROIConfig.hh"

#include <string>

class VehicleROIConfigReader {
  public:
    VehicleROIConfig ReadPathOnly(const std::string& geometryFilePath) const;
};

#endif

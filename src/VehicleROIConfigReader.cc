#include "VehicleROIConfigReader.hh"

VehicleROIConfig VehicleROIConfigReader::ReadPathOnly(const std::string& geometryFilePath) const
{
    VehicleROIConfig config;
    config.geometryFile = geometryFilePath;
    return config;
}

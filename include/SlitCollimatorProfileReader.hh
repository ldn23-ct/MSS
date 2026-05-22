#ifndef SLIT_COLLIMATOR_PROFILE_READER_HH
#define SLIT_COLLIMATOR_PROFILE_READER_HH

#include <string>
#include <vector>

struct XZPoint {
    double x_mm = 0.0;
    double z_mm = 0.0;
};

struct SlitJawProfile {
    std::string jaw_id;
    double y_zero_mm = 0.0;
    std::vector<XZPoint> vertices;
};

struct SlitCollimatorProfile {
    std::string profile_id;
    std::vector<SlitJawProfile> jaws;
};

class SlitCollimatorProfileReader {
  public:
    SlitCollimatorProfileReader() = default;
    SlitCollimatorProfile ReadProfile(const std::string& filePath, const std::string& profileId) const;
};

#endif

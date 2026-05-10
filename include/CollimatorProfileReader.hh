#ifndef COLLIMATOR_PROFILE_READER_HH
#define COLLIMATOR_PROFILE_READER_HH

#include <array>
#include <string>
#include <vector>

struct XZPoint {
    double x_mm = 0.0;
    double z_mm = 0.0;
};

struct PolygonJawProfile {
    std::string jaw_id;
    std::vector<XZPoint> vertices;
};

struct CollimatorProfile {
    std::string profile_id;
    std::array<PolygonJawProfile, 3> jaws;
};

class CollimatorProfileReader {
  public:
    CollimatorProfileReader() = default;

    CollimatorProfile ReadProfile(const std::string& filePath,
                                  const std::string& profileId) const;
};

#endif

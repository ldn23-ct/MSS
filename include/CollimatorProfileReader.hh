#ifndef COLLIMATOR_PROFILE_READER_HH
#define COLLIMATOR_PROFILE_READER_HH

#include <array>
#include <string>

struct XZPoint {
    double x_mm = 0.0;
    double z_mm = 0.0;
};

struct PentagonJawProfile {
    std::string jaw_id;
    std::array<XZPoint, 5> vertices;
};

struct CollimatorProfile {
    std::string profile_id;
    PentagonJawProfile jaw0;
    PentagonJawProfile jaw1;
};

class CollimatorProfileReader {
  public:
    CollimatorProfileReader() = default;

    CollimatorProfile ReadProfile(const std::string& filePath,
                                  const std::string& profileId) const;
};

#endif

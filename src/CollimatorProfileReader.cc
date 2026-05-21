#include "CollimatorProfileReader.hh"

#include <stdexcept>

CollimatorProfile CollimatorProfileReader::ReadProfile(const std::string&,
                                                       const std::string&) const
{
    throw std::runtime_error(
        "CollimatorProfileReader is legacy-isolated in M0; use SlitCollimatorProfileReader for second-round work");
}

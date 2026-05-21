#include "CollimatorBuilder.hh"

#include <stdexcept>

void CollimatorBuilder::Build(const CollimatorProfile&,
                              G4LogicalVolume*,
                              G4Material*) const
{
    throw std::runtime_error(
        "CollimatorBuilder is legacy-isolated in M0; use SlitCollimatorBuilder for second-round work");
}

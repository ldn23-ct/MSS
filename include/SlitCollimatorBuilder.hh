#ifndef SLIT_COLLIMATOR_BUILDER_HH
#define SLIT_COLLIMATOR_BUILDER_HH

#include "ScanPoseManager.hh"
#include "SimulationConfig.hh"
#include "SlitCollimatorProfileReader.hh"

#include <vector>

class G4LogicalVolume;
class G4VPhysicalVolume;
class MaterialManager;

class SlitCollimatorBuilder {
  public:
    SlitCollimatorBuilder() = default;

    std::vector<G4VPhysicalVolume*> Build(
        const SlitCollimatorProfile& profile,
        const CollimatorConfig& collimatorConfig,
        const ScanPose& pose,
        G4LogicalVolume* motherLogical,
        const MaterialManager& materialManager) const;
};

#endif

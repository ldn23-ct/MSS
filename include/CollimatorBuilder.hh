#ifndef COLLIMATOR_BUILDER_HH
#define COLLIMATOR_BUILDER_HH

class G4LogicalVolume;
class G4Material;
struct CollimatorProfile;

class CollimatorBuilder {
  public:
    CollimatorBuilder() = default;

    void Build(const CollimatorProfile& profile,
               G4LogicalVolume* parentLogical,
               G4Material* tungstenMaterial) const;
};

#endif

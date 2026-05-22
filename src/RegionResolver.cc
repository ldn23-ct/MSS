#include "RegionResolver.hh"

#include "RegionRegistry.hh"

RegionResolver::RegionResolver(const RegionRegistry* registry)
    : registry_(registry)
{
}

RegionResolver::RegionResolver(const RegionRegistry& registry)
    : registry_(&registry)
{
}

void RegionResolver::SetRegistry(const RegionRegistry* registry)
{
    registry_ = registry;
}

void RegionResolver::SetVehicleROIVolume(const G4VPhysicalVolume* volume)
{
    vehicleROIVolume_ = volume;
}

std::string RegionResolver::Resolve(const G4VPhysicalVolume* preStepVolume) const
{
    if (preStepVolume == nullptr) {
        return "none";
    }

    if (registry_ != nullptr) {
        const auto regionId = registry_->FindRegionId(preStepVolume);
        if (regionId) {
            return *regionId;
        }
    }

    if (preStepVolume == vehicleROIVolume_) {
        return "vehicle_background_air";
    }

    return "other";
}

std::string RegionResolver::ResolvePreStepVolume(const G4VPhysicalVolume* preStepVolume) const
{
    return Resolve(preStepVolume);
}

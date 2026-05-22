#include "RegionRegistry.hh"

#include <stdexcept>

void RegionRegistry::Register(const G4VPhysicalVolume* volume, const std::string& regionId)
{
    if (volume == nullptr) {
        throw std::runtime_error("cannot register null physical volume");
    }
    if (regionId.empty()) {
        throw std::runtime_error("region_id must be non-empty");
    }

    const auto existing = regions_.find(volume);
    if (existing == regions_.end()) {
        regions_.emplace(volume, regionId);
        return;
    }
    if (existing->second != regionId) {
        throw std::runtime_error("physical volume is already registered with a different region_id");
    }
}

std::optional<std::string> RegionRegistry::FindRegionId(const G4VPhysicalVolume* volume) const
{
    if (volume == nullptr) {
        return std::nullopt;
    }

    const auto found = regions_.find(volume);
    if (found == regions_.end()) {
        return std::nullopt;
    }
    return found->second;
}

bool RegionRegistry::Contains(const G4VPhysicalVolume* volume) const
{
    return volume != nullptr && regions_.find(volume) != regions_.end();
}

void RegionRegistry::Clear()
{
    regions_.clear();
}

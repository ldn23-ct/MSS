#ifndef VEHICLE_ROI_CONFIG_HH
#define VEHICLE_ROI_CONFIG_HH

#include <array>
#include <optional>
#include <string>
#include <vector>

struct Aabb {
    std::array<double, 2> x = {0.0, 0.0};
    std::array<double, 2> y = {0.0, 0.0};
    std::array<double, 2> z = {0.0, 0.0};
};

struct BoxComponentConfig {
    std::string name;
    std::string host;
    std::string shape;
    std::string role;
    std::array<double, 3> center_mm = {0.0, 0.0, 0.0};
    std::array<double, 3> size_mm = {0.0, 0.0, 0.0};
    std::array<double, 3> half_size_mm = {0.0, 0.0, 0.0};
    std::array<double, 3> placement_center_in_host_mm = {0.0, 0.0, 0.0};
    Aabb aabb_mm;
    std::string material;
    std::string region_id;
    bool is_insert = false;
    std::optional<std::string> normal_material;
    std::optional<std::string> abnormal_material;
    std::optional<std::string> normal_region_id;
    std::optional<std::string> abnormal_region_id;
};

struct VehicleROIConfig {
    std::string geometry_file;
    std::string vehicle_model_id;
    BoxComponentConfig root_roi;
    std::vector<BoxComponentConfig> components;
    std::vector<std::string> recommended_target_components;
    std::vector<std::string> detailed_region_ids;
};

#endif

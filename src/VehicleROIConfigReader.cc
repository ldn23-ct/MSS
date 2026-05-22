#include "VehicleROIConfigReader.hh"

#include <algorithm>
#include <array>
#include <cmath>
#include <filesystem>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include <yaml-cpp/yaml.h>

namespace {

constexpr double kTolerance = 1.0e-6;

std::string FieldPath(const std::string& parentPath, const std::string& key)
{
    if (parentPath.empty()) {
        return key;
    }
    return parentPath + "." + key;
}

YAML::Node RequireField(const YAML::Node& parent, const std::string& key, const std::string& parentPath)
{
    if (!parent.IsMap()) {
        throw std::runtime_error(parentPath + " must be a YAML map");
    }

    const YAML::Node node = parent[key];
    if (!node) {
        throw std::runtime_error("missing required field: " + FieldPath(parentPath, key));
    }
    return node;
}

YAML::Node RequireMap(const YAML::Node& parent, const std::string& key, const std::string& parentPath)
{
    const YAML::Node node = RequireField(parent, key, parentPath);
    if (!node.IsMap()) {
        throw std::runtime_error(FieldPath(parentPath, key) + " must be a YAML map");
    }
    return node;
}

YAML::Node RequireSequence(const YAML::Node& parent, const std::string& key, const std::string& parentPath)
{
    const YAML::Node node = RequireField(parent, key, parentPath);
    if (!node.IsSequence()) {
        throw std::runtime_error(FieldPath(parentPath, key) + " must be a YAML sequence");
    }
    return node;
}

template <typename T>
T ReadScalar(const YAML::Node& parent, const std::string& key, const std::string& parentPath)
{
    const YAML::Node node = RequireField(parent, key, parentPath);
    const std::string path = FieldPath(parentPath, key);
    if (!node.IsScalar()) {
        throw std::runtime_error(path + " must be a scalar value");
    }

    try {
        return node.as<T>();
    } catch (const YAML::Exception& error) {
        throw std::runtime_error(path + " has invalid type or value: " + std::string(error.what()));
    }
}

template <std::size_t N>
std::array<double, N> ReadDoubleArray(
    const YAML::Node& parent,
    const std::string& key,
    const std::string& parentPath)
{
    const YAML::Node node = RequireSequence(parent, key, parentPath);
    const std::string path = FieldPath(parentPath, key);
    if (node.size() != N) {
        std::ostringstream message;
        message << path << " must contain " << N << " values";
        throw std::runtime_error(message.str());
    }

    std::array<double, N> values = {};
    for (std::size_t i = 0; i < N; ++i) {
        if (!node[i].IsScalar()) {
            throw std::runtime_error(path + " contains a non-scalar value");
        }
        try {
            values[i] = node[i].as<double>();
        } catch (const YAML::Exception& error) {
            throw std::runtime_error(path + " contains an invalid numeric value: " + std::string(error.what()));
        }
        if (!std::isfinite(values[i])) {
            throw std::runtime_error(path + " contains a non-finite numeric value");
        }
    }
    return values;
}

std::array<double, 2> ReadAabbAxis(const YAML::Node& aabb, const std::string& axis, const std::string& parentPath)
{
    const auto values = ReadDoubleArray<2>(aabb, axis, parentPath);
    if (values[0] >= values[1]) {
        throw std::runtime_error(FieldPath(parentPath, axis) + " must have min < max");
    }
    return values;
}

std::vector<std::string> ReadStringVector(
    const YAML::Node& parent,
    const std::string& key,
    const std::string& parentPath)
{
    const YAML::Node node = RequireSequence(parent, key, parentPath);
    const std::string path = FieldPath(parentPath, key);
    std::vector<std::string> values;
    values.reserve(node.size());
    for (std::size_t i = 0; i < node.size(); ++i) {
        if (!node[i].IsScalar()) {
            throw std::runtime_error(path + " contains a non-scalar value");
        }
        try {
            values.push_back(node[i].as<std::string>());
        } catch (const YAML::Exception& error) {
            throw std::runtime_error(path + " contains an invalid string value: " + std::string(error.what()));
        }
        if (values.back().empty()) {
            throw std::runtime_error(path + " contains an empty string");
        }
    }
    return values;
}

bool NearlyEqual(double lhs, double rhs)
{
    return std::abs(lhs - rhs) <= kTolerance;
}

bool ArraysEqual(const std::array<double, 3>& lhs, const std::array<double, 3>& rhs)
{
    for (std::size_t i = 0; i < lhs.size(); ++i) {
        if (!NearlyEqual(lhs[i], rhs[i])) {
            return false;
        }
    }
    return true;
}

std::array<double, 3> ExpectedHalfSize(const BoxComponentConfig& component)
{
    return {component.size_mm[0] * 0.5, component.size_mm[1] * 0.5, component.size_mm[2] * 0.5};
}

Aabb ExpectedAabb(const BoxComponentConfig& component)
{
    Aabb aabb;
    aabb.x = {component.center_mm[0] - component.size_mm[0] * 0.5,
              component.center_mm[0] + component.size_mm[0] * 0.5};
    aabb.y = {component.center_mm[1] - component.size_mm[1] * 0.5,
              component.center_mm[1] + component.size_mm[1] * 0.5};
    aabb.z = {component.center_mm[2] - component.size_mm[2] * 0.5,
              component.center_mm[2] + component.size_mm[2] * 0.5};
    return aabb;
}

bool AabbEqual(const Aabb& lhs, const Aabb& rhs)
{
    return NearlyEqual(lhs.x[0], rhs.x[0]) && NearlyEqual(lhs.x[1], rhs.x[1])
        && NearlyEqual(lhs.y[0], rhs.y[0]) && NearlyEqual(lhs.y[1], rhs.y[1])
        && NearlyEqual(lhs.z[0], rhs.z[0]) && NearlyEqual(lhs.z[1], rhs.z[1]);
}

bool AxisContains(const std::array<double, 2>& host, const std::array<double, 2>& child)
{
    return child[0] + kTolerance >= host[0] && child[1] <= host[1] + kTolerance;
}

bool Contains(const Aabb& host, const Aabb& child)
{
    return AxisContains(host.x, child.x) && AxisContains(host.y, child.y) && AxisContains(host.z, child.z);
}

bool AxisPositiveOverlap(const std::array<double, 2>& lhs, const std::array<double, 2>& rhs)
{
    return std::max(lhs[0], rhs[0]) < std::min(lhs[1], rhs[1]) - kTolerance;
}

bool PositiveOverlap(const Aabb& lhs, const Aabb& rhs)
{
    return AxisPositiveOverlap(lhs.x, rhs.x) && AxisPositiveOverlap(lhs.y, rhs.y)
        && AxisPositiveOverlap(lhs.z, rhs.z);
}

std::string ReadMaterialOrRegionString(
    const YAML::Node& node,
    const std::string& field,
    const std::string& parentPath)
{
    const YAML::Node value = RequireField(node, field, parentPath);
    const std::string path = FieldPath(parentPath, field);
    if (!value.IsScalar()) {
        throw std::runtime_error(path + " must be a string for non-insert component");
    }
    try {
        auto text = value.as<std::string>();
        if (text.empty()) {
            throw std::runtime_error(path + " must be non-empty");
        }
        return text;
    } catch (const YAML::Exception& error) {
        throw std::runtime_error(path + " has invalid type or value: " + std::string(error.what()));
    }
}

void ReadInsertMaterial(
    const YAML::Node& componentNode,
    const std::string& field,
    const std::string& parentPath,
    std::optional<std::string>& normal,
    std::optional<std::string>& abnormal)
{
    const YAML::Node node = RequireMap(componentNode, field, parentPath);
    normal = ReadScalar<std::string>(node, "normal", FieldPath(parentPath, field));
    abnormal = ReadScalar<std::string>(node, "abnormal", FieldPath(parentPath, field));
    if (normal->empty() || abnormal->empty()) {
        throw std::runtime_error(FieldPath(parentPath, field) + " normal/abnormal values must be non-empty");
    }
}

BoxComponentConfig ReadComponent(const YAML::Node& node, std::size_t index)
{
    if (!node.IsMap()) {
        throw std::runtime_error("components[] entry must be a YAML map");
    }

    const std::string path = "components[" + std::to_string(index) + "]";
    BoxComponentConfig component;
    component.name = ReadScalar<std::string>(node, "name", path);
    component.host = ReadScalar<std::string>(node, "host", path);
    component.shape = ReadScalar<std::string>(node, "shape", path);
    component.center_mm = ReadDoubleArray<3>(node, "center_mm", path);
    component.size_mm = ReadDoubleArray<3>(node, "size_mm", path);
    component.is_insert = ReadScalar<bool>(node, "is_insert", path);
    component.role = ReadScalar<std::string>(node, "role", path);
    component.half_size_mm = ReadDoubleArray<3>(node, "half_size_mm", path);
    component.placement_center_in_host_mm = ReadDoubleArray<3>(node, "placement_center_in_host_mm", path);

    const YAML::Node aabb = RequireMap(node, "aabb_mm", path);
    component.aabb_mm.x = ReadAabbAxis(aabb, "x", FieldPath(path, "aabb_mm"));
    component.aabb_mm.y = ReadAabbAxis(aabb, "y", FieldPath(path, "aabb_mm"));
    component.aabb_mm.z = ReadAabbAxis(aabb, "z", FieldPath(path, "aabb_mm"));

    if (component.name.empty()) {
        throw std::runtime_error(path + ".name must be non-empty");
    }
    if (component.host.empty()) {
        throw std::runtime_error(path + ".host must be non-empty");
    }
    if (component.shape != "box") {
        throw std::runtime_error(path + ".shape must be box");
    }
    if (component.role.empty()) {
        throw std::runtime_error(path + ".role must be non-empty");
    }
    for (double size : component.size_mm) {
        if (size <= 0.0) {
            throw std::runtime_error(path + ".size_mm values must be > 0");
        }
    }

    if (component.is_insert) {
        ReadInsertMaterial(
            node, "material", path, component.normal_material, component.abnormal_material);
        ReadInsertMaterial(
            node, "region_id", path, component.normal_region_id, component.abnormal_region_id);
        component.material = *component.normal_material;
        component.region_id = *component.normal_region_id;
    } else {
        component.material = ReadMaterialOrRegionString(node, "material", path);
        component.region_id = ReadMaterialOrRegionString(node, "region_id", path);
    }

    return component;
}

void ValidateComponentGeometry(const BoxComponentConfig& component)
{
    if (!ArraysEqual(component.half_size_mm, ExpectedHalfSize(component))) {
        throw std::runtime_error(component.name + " half_size_mm does not match size_mm * 0.5");
    }
    if (!AabbEqual(component.aabb_mm, ExpectedAabb(component))) {
        throw std::runtime_error(component.name + " aabb_mm does not match center_mm/size_mm");
    }
}

void ValidateTargets(const VehicleROIConfig& config, const std::optional<std::string>& selectedTarget)
{
    const std::set<std::string> recommended(
        config.recommended_target_components.begin(), config.recommended_target_components.end());
    std::set<std::string> componentNames;
    std::set<std::string> insertNames;
    for (const auto& component : config.components) {
        componentNames.insert(component.name);
        if (component.is_insert) {
            insertNames.insert(component.name);
        }
    }

    for (const auto& target : recommended) {
        if (componentNames.find(target) == componentNames.end()) {
            throw std::runtime_error("recommended target component does not exist: " + target);
        }
        if (insertNames.find(target) == insertNames.end()) {
            throw std::runtime_error("recommended target component is not insert: " + target);
        }
    }

    if (selectedTarget) {
        if (componentNames.find(*selectedTarget) == componentNames.end()) {
            throw std::runtime_error("vehicle.selected_target_component does not exist: " + *selectedTarget);
        }
        if (insertNames.find(*selectedTarget) == insertNames.end()) {
            throw std::runtime_error("vehicle.selected_target_component is not insert: " + *selectedTarget);
        }
        if (recommended.find(*selectedTarget) == recommended.end()) {
            throw std::runtime_error(
                "vehicle.selected_target_component is not in recommended target list: " + *selectedTarget);
        }
    }
}

void ValidateRelationships(VehicleROIConfig& config)
{
    std::map<std::string, const BoxComponentConfig*> byName;
    std::map<std::string, std::vector<const BoxComponentConfig*>> byHost;
    for (const auto& component : config.components) {
        if (!byName.emplace(component.name, &component).second) {
            throw std::runtime_error("duplicate component name: " + component.name);
        }
        byHost[component.host].push_back(&component);
    }

    const auto rootIt = byName.find("VehicleROI");
    if (rootIt == byName.end()) {
        throw std::runtime_error("root VehicleROI component is missing");
    }
    config.root_roi = *rootIt->second;
    if (config.root_roi.host != "World") {
        throw std::runtime_error("VehicleROI host must be World");
    }

    for (const auto& component : config.components) {
        ValidateComponentGeometry(component);
        if (component.name == "VehicleROI") {
            continue;
        }

        const auto hostIt = byName.find(component.host);
        if (hostIt == byName.end()) {
            throw std::runtime_error(component.name + " host does not exist: " + component.host);
        }
        if (!Contains(hostIt->second->aabb_mm, component.aabb_mm)) {
            throw std::runtime_error(component.name + " is not fully contained in host " + component.host);
        }

        const std::array<double, 3> expectedPlacement = {
            component.center_mm[0] - hostIt->second->center_mm[0],
            component.center_mm[1] - hostIt->second->center_mm[1],
            component.center_mm[2] - hostIt->second->center_mm[2]};
        if (!ArraysEqual(component.placement_center_in_host_mm, expectedPlacement)) {
            throw std::runtime_error(
                component.name + " placement_center_in_host_mm does not match component center minus host center");
        }
    }

    for (const auto& hostAndChildren : byHost) {
        const auto& children = hostAndChildren.second;
        for (std::size_t i = 0; i < children.size(); ++i) {
            for (std::size_t j = i + 1; j < children.size(); ++j) {
                if (PositiveOverlap(children[i]->aabb_mm, children[j]->aabb_mm)) {
                    throw std::runtime_error(
                        "positive AABB overlap among siblings under host " + hostAndChildren.first + ": "
                        + children[i]->name + " and " + children[j]->name);
                }
            }
        }
    }
}

void ValidateTopLevelSections(const YAML::Node& root)
{
    static const std::vector<std::string> requiredSections = {
        "schema",
        "metadata",
        "units",
        "coordinate_system",
        "roi",
        "geant4_placement_rules",
        "materials",
        "model_modes",
        "regions",
        "components",
        "validation"};
    for (const auto& section : requiredSections) {
        RequireField(root, section, "");
    }
}

}  // namespace

VehicleROIConfig VehicleROIConfigReader::ReadPathOnly(const std::string& geometryFilePath) const
{
    if (geometryFilePath.empty()) {
        throw std::runtime_error("vehicle ROI geometry path is empty");
    }

    const std::filesystem::path path(geometryFilePath);
    if (!std::filesystem::exists(path)) {
        throw std::runtime_error("vehicle ROI geometry file does not exist: " + geometryFilePath);
    }
    if (!std::filesystem::is_regular_file(path)) {
        throw std::runtime_error("vehicle ROI geometry path is not a regular file: " + geometryFilePath);
    }

    VehicleROIConfig config;
    config.geometry_file = geometryFilePath;
    return config;
}

VehicleROIConfig VehicleROIConfigReader::Read(const std::string& geometryFilePath) const
{
    VehicleROIConfig config = ReadPathOnly(geometryFilePath);

    YAML::Node root;
    try {
        root = YAML::LoadFile(geometryFilePath);
    } catch (const YAML::Exception& error) {
        throw std::runtime_error(
            "failed to read VehicleROI YAML " + geometryFilePath + ": " + std::string(error.what()));
    }
    if (!root.IsMap()) {
        throw std::runtime_error("VehicleROI YAML root must be a map: " + geometryFilePath);
    }
    ValidateTopLevelSections(root);

    const YAML::Node metadata = RequireMap(root, "metadata", "");
    config.vehicle_model_id = ReadScalar<std::string>(metadata, "model_name", "metadata");
    if (config.vehicle_model_id.empty()) {
        throw std::runtime_error("metadata.model_name must be non-empty");
    }

    const YAML::Node regions = RequireMap(root, "regions", "");
    config.detailed_region_ids = ReadStringVector(regions, "detailed_region_ids", "regions");

    const YAML::Node modelModes = RequireMap(root, "model_modes", "");
    const YAML::Node abnormal = RequireMap(modelModes, "abnormal", "model_modes");
    config.recommended_target_components =
        ReadStringVector(abnormal, "recommended_single_target_components", "model_modes.abnormal");

    const YAML::Node components = RequireSequence(root, "components", "");
    if (components.size() == 0) {
        throw std::runtime_error("components must contain at least VehicleROI");
    }
    config.components.reserve(components.size());
    for (std::size_t i = 0; i < components.size(); ++i) {
        config.components.push_back(ReadComponent(components[i], i));
    }

    ValidateRelationships(config);
    ValidateTargets(config, std::nullopt);
    return config;
}

VehicleROIConfig VehicleROIConfigReader::Read(const VehicleRunConfig& vehicleConfig) const
{
    VehicleROIConfig config = Read(vehicleConfig.geometry_file);
    ValidateTargets(config, vehicleConfig.selected_target_component);
    return config;
}

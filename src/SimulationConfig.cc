#include "SimulationConfig.hh"

#include <cmath>
#include <filesystem>
#include <stdexcept>

namespace {

bool IsFinite(double value)
{
    return std::isfinite(value);
}

void RequireFinite(double value, const std::string& field)
{
    if (!IsFinite(value)) {
        throw std::runtime_error(field + " must be finite");
    }
}

}  // namespace

void SimulationConfig::ValidateConfigPathOnly() const
{
    if (configFilePath.empty()) {
        throw std::runtime_error("config path is empty");
    }

    const std::filesystem::path path(configFilePath);
    if (!std::filesystem::exists(path)) {
        throw std::runtime_error("config file does not exist: " + configFilePath);
    }
    if (!std::filesystem::is_regular_file(path)) {
        throw std::runtime_error("config path is not a regular file: " + configFilePath);
    }
}

void SimulationConfig::Validate() const
{
    ValidateConfigPathOnly();

    if (schema_version != 2) {
        throw std::runtime_error("schema_version must be 2");
    }
    if (run.number_of_threads < 1) {
        throw std::runtime_error("run.number_of_threads must be >= 1");
    }
    if (run.n_primary_per_pose <= 0) {
        throw std::runtime_error("run.n_primary_per_pose must be > 0");
    }
    if (run.random_seed < 0) {
        throw std::runtime_error("run.random_seed must be non-negative");
    }

    if (vehicle.geometry_file.empty()) {
        throw std::runtime_error("vehicle.geometry_file must be non-empty");
    }
    if (vehicle.model_type != "normal" && vehicle.model_type != "abnormal") {
        throw std::runtime_error("vehicle.model_type must be normal or abnormal");
    }
    if (vehicle.model_type == "abnormal"
        && (!vehicle.selected_target_component || vehicle.selected_target_component->empty())) {
        throw std::runtime_error("vehicle.selected_target_component is required for abnormal model_type");
    }
    if (vehicle.abnormal_material.empty()) {
        throw std::runtime_error("vehicle.abnormal_material must be non-empty");
    }

    if (pose.mode != "list" && pose.mode != "grid") {
        throw std::runtime_error("pose.mode must be list or grid");
    }
    if (pose.mode == "list"
        && pose.list_head_offset_x_mm.size() != pose.list_head_offset_y_mm.size()) {
        throw std::runtime_error("pose.list.head_offset_x_mm and pose.list.head_offset_y_mm must have the same length");
    }

    if (source.particle != "gamma") {
        throw std::runtime_error("source.particle must be gamma");
    }
    if (source.energy_mode != "mono" && source.energy_mode != "spectrum") {
        throw std::runtime_error("source.energy_mode must be mono or spectrum");
    }
    RequireFinite(source.mono_energy_keV, "source.mono_energy_keV");
    if (source.mono_energy_keV <= 0.0) {
        throw std::runtime_error("source.mono_energy_keV must be > 0");
    }
    if (source.energy_mode == "spectrum" && source.spectrum_file.empty()) {
        throw std::runtime_error("source.spectrum_file must be non-empty for spectrum energy_mode");
    }
    for (std::size_t i = 0; i < source.source_pos_zero_mm.size(); ++i) {
        RequireFinite(source.source_pos_zero_mm[i], "source.source_pos_zero_mm");
    }
    RequireFinite(source.incident_theta_deg, "source.incident_theta_deg");
    if (source.incident_theta_deg <= 0.0 || source.incident_theta_deg > 90.0) {
        throw std::runtime_error("source.incident_theta_deg must satisfy 0 < theta <= 90");
    }
    RequireFinite(source.focal_spot_diameter_mm, "source.focal_spot_diameter_mm");
    if (source.focal_spot_diameter_mm <= 0.0) {
        throw std::runtime_error("source.focal_spot_diameter_mm must be > 0");
    }

    if (collimator.enable) {
        if (collimator.profile_file.empty()) {
            throw std::runtime_error("collimator.profile_file must be non-empty when collimator.enable is true");
        }
        if (collimator.profile_id.empty()) {
            throw std::runtime_error("collimator.profile_id must be non-empty when collimator.enable is true");
        }
    }
    RequireFinite(collimator.jaw_extrusion_length_y_mm, "collimator.jaw_extrusion_length_y_mm");
    if (collimator.jaw_extrusion_length_y_mm <= 0.0) {
        throw std::runtime_error("collimator.jaw_extrusion_length_y_mm must be > 0");
    }

    RequireFinite(detector.detector_z_zero_mm, "detector.detector_z_zero_mm");
    RequireFinite(detector.detector_x_range_zero_mm[0], "detector.detector_x_range_zero_mm");
    RequireFinite(detector.detector_x_range_zero_mm[1], "detector.detector_x_range_zero_mm");
    RequireFinite(detector.detector_y_range_zero_mm[0], "detector.detector_y_range_zero_mm");
    RequireFinite(detector.detector_y_range_zero_mm[1], "detector.detector_y_range_zero_mm");
    if (detector.detector_x_range_zero_mm[0] >= detector.detector_x_range_zero_mm[1]) {
        throw std::runtime_error("detector.detector_x_range_zero_mm must have min < max");
    }
    if (detector.detector_y_range_zero_mm[0] >= detector.detector_y_range_zero_mm[1]) {
        throw std::runtime_error("detector.detector_y_range_zero_mm must have min < max");
    }
    if (detector.accept_direction != "negative_z") {
        throw std::runtime_error("detector.accept_direction must be negative_z");
    }

    if (physics.physics_list.empty()) {
        throw std::runtime_error("physics.physics_list must be non-empty");
    }
    RequireFinite(physics.production_cut_mm, "physics.production_cut_mm");
    if (physics.production_cut_mm <= 0.0) {
        throw std::runtime_error("physics.production_cut_mm must be > 0");
    }

    if (output.output_directory.empty()) {
        throw std::runtime_error("output.output_directory must be non-empty");
    }
    if (output.events_csv_name.empty()) {
        throw std::runtime_error("output.events_csv_name must be non-empty");
    }
    if (output.metadata_yaml_name.empty()) {
        throw std::runtime_error("output.metadata_yaml_name must be non-empty");
    }
    if (output.thread_tmp_directory.empty()) {
        throw std::runtime_error("output.thread_tmp_directory must be non-empty");
    }
}

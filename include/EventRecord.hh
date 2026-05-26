#ifndef EVENT_RECORD_HH
#define EVENT_RECORD_HH

#include "G4ThreeVector.hh"

#include <unordered_map>
#include <limits>
#include <string>

struct ScatterSummary {
    int scatter_count_total = 0;
    int compton_count = 0;
    int rayleigh_count = 0;
    G4ThreeVector first_scatter_pos = G4ThreeVector(
        std::numeric_limits<double>::quiet_NaN(),
        std::numeric_limits<double>::quiet_NaN(),
        std::numeric_limits<double>::quiet_NaN());
    G4ThreeVector last_scatter_pos = G4ThreeVector(
        std::numeric_limits<double>::quiet_NaN(),
        std::numeric_limits<double>::quiet_NaN(),
        std::numeric_limits<double>::quiet_NaN());
    std::string first_scatter_region_id = "none";
    std::string last_scatter_region_id = "none";
};

struct DetectorHitRecord {
    bool detected = false;
    int hit_id = -1;
    double det_x_mm = std::numeric_limits<double>::quiet_NaN();
    double det_y_mm = std::numeric_limits<double>::quiet_NaN();
    double det_z_mm = std::numeric_limits<double>::quiet_NaN();
    double det_energy_keV = std::numeric_limits<double>::quiet_NaN();
};

struct GammaTrackSummary {
    int track_id = -1;
    int parent_id = -1;
    bool is_primary_gamma = false;
    std::string gamma_source_type = "none";
    std::string gamma_source_process = "none";
    G4ThreeVector gamma_source_pos = G4ThreeVector(
        std::numeric_limits<double>::quiet_NaN(),
        std::numeric_limits<double>::quiet_NaN(),
        std::numeric_limits<double>::quiet_NaN());
    std::string gamma_source_region_id = "none";
    ScatterSummary scatter;
    DetectorHitRecord hit;
};

struct EventRecord {
    int event_id = -1;
    int next_hit_id = 0;
    std::unordered_map<int, GammaTrackSummary> gamma_tracks;
};

#endif

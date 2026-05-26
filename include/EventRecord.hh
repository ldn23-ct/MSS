#ifndef EVENT_RECORD_HH
#define EVENT_RECORD_HH

#include "G4ThreeVector.hh"

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
    double det_x_mm = std::numeric_limits<double>::quiet_NaN();
    double det_y_mm = std::numeric_limits<double>::quiet_NaN();
    double det_z_mm = std::numeric_limits<double>::quiet_NaN();
    double det_energy_keV = std::numeric_limits<double>::quiet_NaN();
};

struct EventRecord {
    int event_id = -1;
    ScatterSummary scatter;
    DetectorHitRecord hit;
};

#endif

#ifndef EVENT_RECORD_HH
#define EVENT_RECORD_HH

#include <string>

struct EventRecord {
    long event_id = -1;
    bool detected = false;
    std::string pose_id;
};

#endif

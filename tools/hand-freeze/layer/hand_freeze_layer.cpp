// hand_freeze_layer.cpp -- an OpenXR API layer that holds both controllers still on request, in any OpenXR game.
//
// Why (Tefa, 2026-10-13): tuning hand poses in VR means moving sliders with a mouse while the in-game hands stay where
// they should be. Holding two controllers in one hand while doing that is miserable. With this layer, the Hand Freeze
// desktop app counts down (so the controllers can be held comfortably in place), then every controller stays where it
// was at that moment, fixed in the ROOM; the headset keeps tracking, so the player can lean in and look around the
// hands. The game itself never pauses.
//
// How: the layer sits between the game and the OpenXR runtime (registered as an implicit layer by the app). Every
// space made by xrCreateActionSpace is a controller (or other tracked-device) pose; reference spaces (view, local,
// stage) are the headset and the room and are never touched. At the first pose call after a freeze begins, each
// controller's pose is taken in a LOCAL reference space the layer makes for that session (fixed in the room). While
// frozen, any request "controller relative to base" is answered as (base relative to LOCAL, live)^-1 x (kept pose), so
// a game asking relative to the head (VIEW) sees the hand stay in the room as the head moves, not stuck to the face.
// Velocities are zeroed. The switch is a small shared-memory block (shared.h) the app writes; the layer writes a
// heartbeat into it so the app can say which game is connected.
// v2 (2026-10-13): LEFT / RIGHT / BOTH. Each controller space is sorted into a hand once: by the subaction path it was
// made with (/user/hand/left or /right), else by where its action is bound (xrEnumerateBoundSourcesForAction). A space
// whose hand cannot be told is held only when both hands are frozen.
#define XR_NO_PROTOTYPES
#include <windows.h>
#include <openxr/openxr.h>
#include <openxr/openxr_loader_negotiation.h>

#include <cstring>
#include <map>
#include <mutex>
#include <type_traits>

#include "../shared.h"

namespace {

PFN_xrGetInstanceProcAddr g_next_gipa = nullptr;
PFN_xrCreateActionSpace g_next_create_action_space = nullptr;
PFN_xrCreateReferenceSpace g_next_create_reference_space = nullptr;
PFN_xrDestroySpace g_next_destroy_space = nullptr;
PFN_xrDestroySession g_next_destroy_session = nullptr;
PFN_xrLocateSpace g_next_locate_space = nullptr;
PFN_xrLocateSpaces g_next_locate_spaces = nullptr;
PFN_xrLocateSpacesKHR g_next_locate_spaces_khr = nullptr;
PFN_xrPathToString g_next_path_to_string = nullptr;
PFN_xrEnumerateBoundSourcesForAction g_next_bound_sources = nullptr;
XrInstance g_instance = XR_NULL_HANDLE;

enum Hand : int { HAND_NOT_LOOKED = 0, HAND_LEFT = 1, HAND_RIGHT = 2, HAND_UNKNOWN = 3 };
struct Controller {
    XrSession session; XrAction action; XrPath subaction;
    int hand = HAND_NOT_LOOKED;
    bool kept = false; LONG kept_generation = 0; XrPosef pose_in_room{};
};
std::recursive_mutex g_mtx;
std::map<XrSpace, Controller> g_controllers;   // every space made by xrCreateActionSpace
std::map<XrSession, XrSpace> g_room;           // our own LOCAL space per session: the frame the kept poses live in

// ---- pose maths (unit quaternions, metres) -----------------------------------------------------------------------
XrQuaternionf qmul(XrQuaternionf a, XrQuaternionf b) {
    return {a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y, a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x,
            a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w, a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z};
}
XrQuaternionf qinv(XrQuaternionf q) { return {-q.x, -q.y, -q.z, q.w}; }
XrVector3f rot(XrQuaternionf q, XrVector3f v) {
    const XrQuaternionf r = qmul(qmul(q, {v.x, v.y, v.z, 0}), qinv(q));
    return {r.x, r.y, r.z};
}
// pose of B in A's frame, given both in the room: inverse(a) x b
XrPosef relative(const XrPosef& a, const XrPosef& b) {
    const XrQuaternionf ia = qinv(a.orientation);
    const XrVector3f d{b.position.x - a.position.x, b.position.y - a.position.y, b.position.z - a.position.z};
    return {qmul(ia, b.orientation), rot(ia, d)};
}
constexpr XrSpaceLocationFlags kValid = XR_SPACE_LOCATION_POSITION_VALID_BIT | XR_SPACE_LOCATION_ORIENTATION_VALID_BIT;

// ---- the shared switch -------------------------------------------------------------------------------------------
HandFreezeShared* g_shared = nullptr;

HandFreezeShared* shared() {
    if (g_shared != nullptr) return g_shared;
    HANDLE h = CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE, 0, sizeof(HandFreezeShared), HAND_FREEZE_MAPPING_NAME);
    if (h == nullptr) return nullptr;
    auto* p = static_cast<HandFreezeShared*>(MapViewOfFile(h, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(HandFreezeShared)));
    if (p == nullptr) { CloseHandle(h); return nullptr; }
    if (p->magic != HAND_FREEZE_MAGIC) { p->version = HAND_FREEZE_VERSION; p->magic = HAND_FREEZE_MAGIC; }   // first one in sets it up
    g_shared = p;   // the handle stays open for the life of the process, on purpose
    return p;
}

void heartbeat() {
    auto* s = shared();
    if (s == nullptr) return;
    s->layer_heartbeat_ms = GetTickCount64();
    s->layer_pid = GetCurrentProcessId();
    {
        std::lock_guard _{g_mtx};
        LONG left = 0, right = 0;
        for (const auto& c : g_controllers) { left += c.second.hand == HAND_LEFT; right += c.second.hand == HAND_RIGHT; }
        s->controller_spaces = static_cast<LONG>(g_controllers.size());
        s->left_spaces = left;
        s->right_spaces = right;
    }
    if (s->game_name[0] == 0 || s->game_name_pid != s->layer_pid) {
        wchar_t path[MAX_PATH]{};
        GetModuleFileNameW(nullptr, path, MAX_PATH);
        const wchar_t* name = wcsrchr(path, L'\\');
        name = name ? name + 1 : path;
        wcsncpy_s(s->game_name, name, _TRUNCATE);
        s->game_name_pid = s->layer_pid;
    }
}

// which hands are held right now (HAND_FREEZE_LEFT / _RIGHT bits); 0 = none
LONG frozen_now() {
    auto* s = shared();
    return s == nullptr ? 0 : s->frozen;
}

int hand_of_path(XrPath path) {
    if (path == XR_NULL_PATH || g_next_path_to_string == nullptr) return HAND_UNKNOWN;
    char text[XR_MAX_PATH_LENGTH]{};
    uint32_t n = 0;
    if (XR_FAILED(g_next_path_to_string(g_instance, path, XR_MAX_PATH_LENGTH, &n, text))) return HAND_UNKNOWN;
    if (std::strncmp(text, "/user/hand/left", 15) == 0) return HAND_LEFT;
    if (std::strncmp(text, "/user/hand/right", 16) == 0) return HAND_RIGHT;
    return HAND_UNKNOWN;
}

// sort a controller space into a hand, once it can be told (bindings exist only after the game syncs its actions)
int hand_of(Controller& c) {
    if (c.hand == HAND_LEFT || c.hand == HAND_RIGHT) return c.hand;
    int hand = hand_of_path(c.subaction);
    if (hand == HAND_UNKNOWN && g_next_bound_sources != nullptr) {
        XrBoundSourcesForActionEnumerateInfo info{XR_TYPE_BOUND_SOURCES_FOR_ACTION_ENUMERATE_INFO};
        info.action = c.action;
        XrPath sources[16]{};
        uint32_t n = 0;
        if (XR_SUCCEEDED(g_next_bound_sources(c.session, &info, 16, &n, sources)) && n > 0) {
            int seen = hand_of_path(sources[0]);
            for (uint32_t i = 1; i < n && i < 16; ++i) if (hand_of_path(sources[i]) != seen) seen = HAND_UNKNOWN;
            hand = seen;
        }
    }
    c.hand = hand;
    return hand;
}

// The held answer for "controller `space` relative to `base`" at `time`. False = answer live (not a controller, the
// base is itself a controller, or no usable pose yet).
bool held_pose(XrSpace space, XrSpace base, XrTime time, LONG mask, XrPosef& out) {
    std::lock_guard _{g_mtx};
    auto c = g_controllers.find(space);
    if (c == g_controllers.end() || g_controllers.count(base) != 0) return false;
    auto r = g_room.find(c->second.session);
    if (r == g_room.end()) return false;
    const int hand = hand_of(c->second);
    const LONG both = HAND_FREEZE_LEFT | HAND_FREEZE_RIGHT;
    const bool wanted = hand == HAND_LEFT ? (mask & HAND_FREEZE_LEFT) != 0 : hand == HAND_RIGHT ? (mask & HAND_FREEZE_RIGHT) != 0 : (mask & both) == both;
    if (!wanted) return false;
    auto* s = shared();
    const LONG generation = hand == HAND_LEFT ? s->generation_left : hand == HAND_RIGHT ? s->generation_right
                                              : s->generation_left * 65536 + s->generation_right;
    if (c->second.kept && c->second.kept_generation != generation) c->second.kept = false;   // a new freeze: fresh pose
    if (!c->second.kept) {
        XrSpaceLocation now{XR_TYPE_SPACE_LOCATION};
        if (XR_FAILED(g_next_locate_space(space, r->second, time, &now)) || (now.locationFlags & kValid) != kValid) return false;
        c->second.pose_in_room = now.pose;
        c->second.kept = true;
        c->second.kept_generation = generation;
        InterlockedIncrement(&s->poses_held);
    }
    XrSpaceLocation b{XR_TYPE_SPACE_LOCATION};   // where the base is in the room right now (the head keeps moving)
    if (XR_FAILED(g_next_locate_space(base, r->second, time, &b)) || (b.locationFlags & kValid) != kValid) return false;
    out = relative(b.pose, c->second.pose_in_room);
    return true;
}

// ---- the hooked functions ----------------------------------------------------------------------------------------
XRAPI_ATTR XrResult XRAPI_CALL hf_xrCreateActionSpace(XrSession session, const XrActionSpaceCreateInfo* info, XrSpace* space) {
    const XrResult r = g_next_create_action_space(session, info, space);
    if (XR_FAILED(r) || space == nullptr) return r;
    std::lock_guard _{g_mtx};
    Controller c{};
    c.session = session;
    c.action = info != nullptr ? info->action : XR_NULL_HANDLE;
    c.subaction = info != nullptr ? info->subactionPath : XR_NULL_PATH;
    g_controllers[*space] = c;
    if (g_room.count(session) == 0 && g_next_create_reference_space != nullptr) {
        XrReferenceSpaceCreateInfo ci{XR_TYPE_REFERENCE_SPACE_CREATE_INFO};
        ci.referenceSpaceType = XR_REFERENCE_SPACE_TYPE_LOCAL;
        ci.poseInReferenceSpace.orientation.w = 1.0f;
        XrSpace room = XR_NULL_HANDLE;
        if (XR_SUCCEEDED(g_next_create_reference_space(session, &ci, &room))) g_room[session] = room;
    }
    return r;
}

XRAPI_ATTR XrResult XRAPI_CALL hf_xrDestroySpace(XrSpace space) {
    {
        std::lock_guard _{g_mtx};
        g_controllers.erase(space);
    }
    return g_next_destroy_space(space);
}

XRAPI_ATTR XrResult XRAPI_CALL hf_xrDestroySession(XrSession session) {
    {
        std::lock_guard _{g_mtx};
        g_room.erase(session);   // the runtime destroys the session's spaces with it
        for (auto it = g_controllers.begin(); it != g_controllers.end();) {
            if (it->second.session == session) it = g_controllers.erase(it); else ++it;
        }
    }
    return g_next_destroy_session(session);
}

void zero_velocity(XrSpaceVelocity* v) { v->linearVelocity = {0, 0, 0}; v->angularVelocity = {0, 0, 0}; }

XRAPI_ATTR XrResult XRAPI_CALL hf_xrLocateSpace(XrSpace space, XrSpace base, XrTime time, XrSpaceLocation* location) {
    const XrResult r = g_next_locate_space(space, base, time, location);
    heartbeat();
    XrPosef held{};
    const LONG mask = XR_SUCCEEDED(r) ? frozen_now() : 0;
    if (location == nullptr || mask == 0 || !held_pose(space, base, time, mask, held)) return r;
    location->pose = held;
    location->locationFlags |= kValid | XR_SPACE_LOCATION_POSITION_TRACKED_BIT | XR_SPACE_LOCATION_ORIENTATION_TRACKED_BIT;
    for (auto* n = static_cast<XrBaseOutStructure*>(location->next); n != nullptr; n = n->next) {
        if (n->type == XR_TYPE_SPACE_VELOCITY) zero_velocity(reinterpret_cast<XrSpaceVelocity*>(n));
    }
    return r;
}

XrResult locate_spaces(PFN_xrLocateSpaces next, XrSession session, const XrSpacesLocateInfo* info, XrSpaceLocations* out) {
    const XrResult r = next(session, info, out);
    heartbeat();
    const LONG mask = XR_SUCCEEDED(r) ? frozen_now() : 0;
    if (info == nullptr || out == nullptr || out->locations == nullptr || mask == 0) return r;
    XrSpaceVelocities* vel = nullptr;
    for (auto* n = static_cast<XrBaseOutStructure*>(out->next); n != nullptr; n = n->next) {
        if (n->type == XR_TYPE_SPACE_VELOCITIES) vel = reinterpret_cast<XrSpaceVelocities*>(n);
    }
    const uint32_t count = info->spaceCount < out->locationCount ? info->spaceCount : out->locationCount;
    for (uint32_t i = 0; i < count; ++i) {
        XrPosef held{};
        if (!held_pose(info->spaces[i], info->baseSpace, info->time, mask, held)) continue;
        out->locations[i].pose = held;
        out->locations[i].locationFlags |= kValid | XR_SPACE_LOCATION_POSITION_TRACKED_BIT | XR_SPACE_LOCATION_ORIENTATION_TRACKED_BIT;
        if (vel != nullptr && vel->velocities != nullptr && i < vel->velocityCount) {
            vel->velocities[i].linearVelocity = {0, 0, 0};
            vel->velocities[i].angularVelocity = {0, 0, 0};
        }
    }
    return r;
}
XRAPI_ATTR XrResult XRAPI_CALL hf_xrLocateSpaces(XrSession s, const XrSpacesLocateInfo* i, XrSpaceLocations* o) { return locate_spaces(g_next_locate_spaces, s, i, o); }
XRAPI_ATTR XrResult XRAPI_CALL hf_xrLocateSpacesKHR(XrSession s, const XrSpacesLocateInfo* i, XrSpaceLocations* o) { return locate_spaces(g_next_locate_spaces_khr, s, i, o); }

XRAPI_ATTR XrResult XRAPI_CALL hf_xrGetInstanceProcAddr(XrInstance instance, const char* name, PFN_xrVoidFunction* function) {
    const XrResult r = g_next_gipa(instance, name, function);
    if (XR_FAILED(r) || function == nullptr || *function == nullptr || name == nullptr) return r;
    // ours only for functions the runtime really has, so a missing extension stays missing
    struct Hook { const char* name; PFN_xrVoidFunction ours; PFN_xrVoidFunction* next; };
    static const Hook hooks[] = {
        {"xrCreateActionSpace", (PFN_xrVoidFunction)hf_xrCreateActionSpace, (PFN_xrVoidFunction*)&g_next_create_action_space},
        {"xrDestroySpace", (PFN_xrVoidFunction)hf_xrDestroySpace, (PFN_xrVoidFunction*)&g_next_destroy_space},
        {"xrDestroySession", (PFN_xrVoidFunction)hf_xrDestroySession, (PFN_xrVoidFunction*)&g_next_destroy_session},
        {"xrLocateSpace", (PFN_xrVoidFunction)hf_xrLocateSpace, (PFN_xrVoidFunction*)&g_next_locate_space},
        {"xrLocateSpaces", (PFN_xrVoidFunction)hf_xrLocateSpaces, (PFN_xrVoidFunction*)&g_next_locate_spaces},
        {"xrLocateSpacesKHR", (PFN_xrVoidFunction)hf_xrLocateSpacesKHR, (PFN_xrVoidFunction*)&g_next_locate_spaces_khr},
    };
    for (const auto& h : hooks) {
        if (std::strcmp(name, h.name) == 0) { *h.next = *function; *function = h.ours; break; }
    }
    return r;
}

// the functions the layer itself calls, fetched once the instance exists (the game may never ask for some of them)
void fetch_next(XrInstance instance) {
    auto get = [&](const char* n, auto& slot) {
        PFN_xrVoidFunction f = nullptr;
        if (slot == nullptr && XR_SUCCEEDED(g_next_gipa(instance, n, &f)) && f != nullptr) slot = reinterpret_cast<std::remove_reference_t<decltype(slot)>>(f);
    };
    get("xrCreateReferenceSpace", g_next_create_reference_space);
    get("xrLocateSpace", g_next_locate_space);
    get("xrCreateActionSpace", g_next_create_action_space);
    get("xrDestroySpace", g_next_destroy_space);
    get("xrDestroySession", g_next_destroy_session);
    get("xrPathToString", g_next_path_to_string);
    get("xrEnumerateBoundSourcesForAction", g_next_bound_sources);
    g_instance = instance;
}

XRAPI_ATTR XrResult XRAPI_CALL hf_xrCreateApiLayerInstance(const XrInstanceCreateInfo* info, const XrApiLayerCreateInfo* layer_info, XrInstance* instance) {
    if (layer_info == nullptr || layer_info->nextInfo == nullptr) return XR_ERROR_INITIALIZATION_FAILED;
    g_next_gipa = layer_info->nextInfo->nextGetInstanceProcAddr;
    XrApiLayerCreateInfo next_info = *layer_info;   // the next layer down gets the chain one step further on
    next_info.nextInfo = layer_info->nextInfo->next;
    const XrResult r = layer_info->nextInfo->nextCreateApiLayerInstance(info, &next_info, instance);
    if (XR_SUCCEEDED(r) && instance != nullptr) fetch_next(*instance);
    return r;
}

} // namespace

extern "C" __declspec(dllexport) XrResult XRAPI_CALL xrNegotiateLoaderApiLayerInterface(const XrNegotiateLoaderInfo* loader_info, const char* /*layer_name*/, XrNegotiateApiLayerRequest* request) {
    if (loader_info == nullptr || request == nullptr || loader_info->structType != XR_LOADER_INTERFACE_STRUCT_LOADER_INFO ||
        request->structType != XR_LOADER_INTERFACE_STRUCT_API_LAYER_REQUEST ||
        loader_info->minInterfaceVersion > XR_CURRENT_LOADER_API_LAYER_VERSION || loader_info->maxInterfaceVersion < XR_CURRENT_LOADER_API_LAYER_VERSION) {
        return XR_ERROR_INITIALIZATION_FAILED;
    }
    request->layerInterfaceVersion = XR_CURRENT_LOADER_API_LAYER_VERSION;
    request->layerApiVersion = loader_info->maxApiVersion < XR_CURRENT_API_VERSION ? loader_info->maxApiVersion : XR_CURRENT_API_VERSION;
    request->getInstanceProcAddr = hf_xrGetInstanceProcAddr;
    request->createApiLayerInstance = hf_xrCreateApiLayerInstance;
    return XR_SUCCESS;
}

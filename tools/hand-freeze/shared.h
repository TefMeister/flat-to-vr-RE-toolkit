// shared.h -- the switch between the Hand Freeze app and the OpenXR layer: one small shared-memory block per Windows
// session. The app writes `frozen` and `generation`; the layer (inside the game) writes the rest. The C# app reads and
// writes it by the byte offsets in the comments, so the layout must never change without bumping HAND_FREEZE_VERSION.
#pragma once
#include <windows.h>
#include <cstdint>

#define HAND_FREEZE_MAPPING_NAME L"Local\\FlatToVR_HandFreeze_v1"
#define HAND_FREEZE_MAGIC 0x5A465248u   // "HRFZ"
#define HAND_FREEZE_VERSION 1u

#pragma pack(push, 4)
struct HandFreezeShared {
    uint32_t magic;               //  0
    uint32_t version;             //  4
    volatile LONG frozen;         //  8  app: 1 = hold the controllers still
    volatile LONG generation;     // 12  app: +1 on every new freeze, so the layer takes fresh poses
    uint64_t layer_heartbeat_ms;  // 16  layer: GetTickCount64() at its last pose call
    uint32_t layer_pid;           // 24  layer: the game's process id
    volatile LONG controller_spaces; // 28 layer: controller spaces the game made
    volatile LONG poses_held;     // 32  layer: poses taken since the layer loaded (rises at each freeze)
    uint32_t game_name_pid;       // 36  layer: whose name is in game_name
    wchar_t game_name[64];        // 40  layer: the game's exe name
};                                // 168 bytes
#pragma pack(pop)
static_assert(sizeof(HandFreezeShared) == 168, "the app reads this layout by offset");

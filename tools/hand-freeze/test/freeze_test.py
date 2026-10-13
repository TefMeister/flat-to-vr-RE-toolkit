"""freeze_test.py -- does the Hand Freeze layer really hold the controllers, and only while asked?

Runs a tiny OpenXR app against a runtime (the OpenXR Simulator by default) with the layer switched on for THIS process
only (XR_API_LAYER_PATH + XR_ENABLE_API_LAYERS; the registry is not touched). It makes both controller pose spaces,
then in three phases -- free, frozen, free again -- locates them against STAGE (the room) and VIEW (the head) each
frame. Something must move during the run for the result to mean anything: with the simulator, switch on its pose
sweep (MCP enable_pose_sweep) while this runs. A held controller is the same in the room whatever the head does, so
during the frozen phase its STAGE pose must not change at all; in the free phases at least one of the two readings
should change as the head sweeps (else nothing was moving and the test proves nothing -- it says so).

    python freeze_test.py [--runtime <runtime json>] [--free 6] [--frozen 10]
Exit 0 = PASS. Needs pyopenxr, glfw, PyOpenGL (as openxr-probe).
"""
import argparse
import ctypes
import json
import mmap
import os
import struct
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LAYER_NAME = "XR_APILAYER_FLATTOVR_hand_freeze"
SIM_RUNTIME = r"D:\claude video game stuff\tools\OpenXR-Simulator\openxr_simulator.json"


def shared_block():
    m = mmap.mmap(-1, 168, tagname="Local\\FlatToVR_HandFreeze_v1")
    if struct.unpack_from("<I", m, 0)[0] != 0x5A465248:
        struct.pack_into("<II", m, 0, 0x5A465248, 1)
    return m


def set_frozen(m, on):
    if on:
        struct.pack_into("<i", m, 12, struct.unpack_from("<i", m, 12)[0] + 1)
    struct.pack_into("<i", m, 8, 1 if on else 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runtime", default=SIM_RUNTIME)
    ap.add_argument("--dll", default=os.path.join(HERE, "..", "dist", "hand_freeze_layer.dll"))
    ap.add_argument("--free", type=float, default=6.0)
    ap.add_argument("--frozen", type=float, default=10.0)
    ap.add_argument("--implicit", action="store_true", help="use the layer as the app registers it (ON button), not just for this process")
    args = ap.parse_args()

    layer_dir = tempfile.mkdtemp(prefix="handfreeze-test-")
    with open(os.path.join(layer_dir, "hand_freeze_layer.json"), "w") as f:
        json.dump({"file_format_version": "1.0.0", "api_layer": {
            "name": LAYER_NAME, "library_path": os.path.abspath(args.dll), "api_version": "1.0",
            "implementation_version": "1", "description": "Hand Freeze (test)"}}, f)
    os.environ["XR_RUNTIME_JSON"] = args.runtime
    if not args.implicit:
        os.environ["XR_API_LAYER_PATH"] = layer_dir
        os.environ["XR_ENABLE_API_LAYERS"] = LAYER_NAME

    import glfw
    import xr
    from OpenGL import GL, WGL
    from xr.utils import SessionStateManager

    layers = [l.layer_name.decode() if isinstance(l.layer_name, bytes) else l.layer_name
              for l in xr.enumerate_api_layer_properties()]
    print("layers the loader sees:", layers)
    if LAYER_NAME not in layers:
        print("FAIL: the layer was not found by the loader")
        return 1

    shm = shared_block()
    set_frozen(shm, False)

    instance = xr.create_instance(xr.InstanceCreateInfo(enabled_extension_names=[xr.KHR_OPENGL_ENABLE_EXTENSION_NAME]))
    system_id = xr.get_system(instance, xr.SystemGetInfo(form_factor=xr.FormFactor.HEAD_MOUNTED_DISPLAY))
    cfg = xr.ViewConfigurationType.PRIMARY_STEREO
    views_cfg = xr.enumerate_view_configuration_views(instance, system_id, cfg)
    xr.get_opengl_graphics_requirements_khr(instance, system_id)
    glfw.init()
    glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
    window = glfw.create_window(320, 240, "freeze_test", None, None)
    glfw.make_context_current(window)
    binding = xr.GraphicsBindingOpenGLWin32KHR(h_dc=WGL.wglGetCurrentDC(), h_glrc=WGL.wglGetCurrentContext())
    session = xr.create_session(instance, xr.SessionCreateInfo(system_id=system_id, next=ctypes.cast(ctypes.pointer(binding), ctypes.c_void_p)))
    stage = xr.create_reference_space(session, xr.ReferenceSpaceCreateInfo(reference_space_type=xr.ReferenceSpaceType.STAGE))
    view = xr.create_reference_space(session, xr.ReferenceSpaceCreateInfo(reference_space_type=xr.ReferenceSpaceType.VIEW))

    # controllers: one pose action on both hands, simple controller grip
    hands = [xr.string_to_path(instance, "/user/hand/left"), xr.string_to_path(instance, "/user/hand/right")]
    aset = xr.create_action_set(instance, xr.ActionSetCreateInfo(action_set_name="test", localized_action_set_name="test", priority=0))
    pose = xr.create_action(aset, xr.ActionCreateInfo(action_type=xr.ActionType.POSE_INPUT, action_name="hand_pose",
                                                      localized_action_name="hand pose", subaction_paths=hands))
    xr.suggest_interaction_profile_bindings(instance, xr.InteractionProfileSuggestedBinding(
        interaction_profile=xr.string_to_path(instance, "/interaction_profiles/khr/simple_controller"),
        suggested_bindings=[xr.ActionSuggestedBinding(pose, xr.string_to_path(instance, "/user/hand/left/input/grip/pose")),
                            xr.ActionSuggestedBinding(pose, xr.string_to_path(instance, "/user/hand/right/input/grip/pose"))]))
    xr.attach_session_action_sets(session, xr.SessionActionSetsAttachInfo(action_sets=[aset]))
    hand_spaces = [xr.create_action_space(session, xr.ActionSpaceCreateInfo(action=pose, subaction_path=h)) for h in hands]

    fmt = xr.enumerate_swapchain_formats(session)[0]
    swapchains, images = [], []
    for c in views_cfg:
        sc = xr.create_swapchain(session, xr.SwapchainCreateInfo(usage_flags=xr.SwapchainUsageFlags.COLOR_ATTACHMENT_BIT, format=fmt,
                                 sample_count=1, width=c.recommended_image_rect_width, height=c.recommended_image_rect_height,
                                 face_count=1, array_size=1, mip_count=1))
        swapchains.append(sc)
        images.append(xr.enumerate_swapchain_images(sc, xr.SwapchainImageOpenGLKHR))

    mgr = SessionStateManager(instance, session, cfg)
    phases = [("free", args.free), ("frozen", args.frozen), ("free again", args.free)]
    samples = {name: [] for name, _ in phases}
    phase_i, phase_start, started = 0, None, False
    print("READY: start moving the simulator's head now (pose sweep)", flush=True)
    try:
        while phase_i < len(phases):
            glfw.poll_events()
            while True:
                try:
                    mgr.handle_xr_event(xr.poll_event(instance))
                except xr.EventUnavailable:
                    break
            fs = mgr.begin_frame()
            if fs is None:
                time.sleep(0.005)
                continue
            now = time.perf_counter()
            if phase_start is None:
                phase_start = now
            name, length = phases[phase_i]
            if now - phase_start >= length:
                phase_i += 1
                phase_start = now
                if phase_i < len(phases):
                    set_frozen(shm, phases[phase_i][0] == "frozen")
                    print("phase:", phases[phase_i][0], flush=True)
                xr.end_frame(session, xr.FrameEndInfo(display_time=fs.predicted_display_time, environment_blend_mode=xr.EnvironmentBlendMode.OPAQUE, layers=[]))
                continue
            xr.sync_actions(session, xr.ActionsSyncInfo(active_action_sets=[xr.ActiveActionSet(aset, xr.NULL_PATH)]))
            row = []
            for hs in hand_spaces:
                for base in (stage, view):
                    loc = xr.locate_space(hs, base, fs.predicted_display_time)
                    p, q = loc.pose.position, loc.pose.orientation
                    row.append((int(loc.location_flags), p.x, p.y, p.z, q.x, q.y, q.z, q.w))
            samples[name].append(row)
            xr.end_frame(session, xr.FrameEndInfo(display_time=fs.predicted_display_time, environment_blend_mode=xr.EnvironmentBlendMode.OPAQUE, layers=[]))
    except SessionStateManager.ExitRenderLoop:
        print("runtime ended the session early")
    set_frozen(shm, False)
    held = struct.unpack_from("<i", shm, 32)[0]
    spaces = struct.unpack_from("<i", shm, 28)[0]

    def spread(rows, k):   # largest change of reading k (0 L-stage, 1 L-view, 2 R-stage, 3 R-view) within a phase
        if not rows:
            return 0.0
        first = rows[0][k][1:]
        return max(max(abs(a - b) for a, b in zip(r[k][1:], first)) for r in rows)

    labels = ["left in room", "left vs head", "right in room", "right vs head"]
    print("\ncontroller spaces the layer saw: %d, poses it held: %d" % (spaces, held))
    print("first reading flags/pose:", samples["free"][0] if samples["free"] else None)
    for name, _ in phases:
        print("%-11s %4d frames  " % (name, len(samples[name])) + "  ".join("%s %.4f" % (labels[k], spread(samples[name], k)) for k in range(4)))
    # The simulator's controllers sit at a fixed offset from the head's POSITION (not its turn), so moving the head
    # (MCP set_head_pose x=...) moves them in the room. Free: they must move in the room. Frozen: they must not move in
    # the room (to float precision, the layer does a little maths) while their pose relative to the head does change
    # (the head moved, the hands stayed: not glued to the face).
    free_room = max(spread(samples[p], k) for p in ("free", "free again") for k in (0, 2))
    frozen_room = max(spread(samples["frozen"], k) for k in (0, 2))
    frozen_head = max(spread(samples["frozen"], k) for k in (1, 3))
    print("free: hands moved %.4f m in the room; frozen: %.6f m in the room, %.4f relative to the head" % (free_room, frozen_room, frozen_head))
    if free_room < 1e-3 or frozen_head < 1e-3:
        print("INCONCLUSIVE: move the head's position in every phase (set_head_pose), or nothing is shown")
        return 2
    ok = frozen_room < 1e-4 and held >= 2
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())

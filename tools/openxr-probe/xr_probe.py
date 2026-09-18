"""xr_probe.py - a pass/fail smoke test for whichever OpenXR runtime is active.

Pattern borrowed, with thanks, from webhead2oo9's probe/xr_probe.cpp in his fork of
OpenXR-Simulator (https://github.com/webhead2oo9/OpenXR-Simulator): extract the contract
a VR mod needs from the runtime, replay it, and make the answer an exit code - so a whole
class of failures is caught at a desk instead of in a headset.

Exit 0 = the runtime advertised what we need, gave two stereo views, and accepted the
         requested number of real projection-layer frames.
Exit 1 = it did not; the reason is printed.

Usage:
    python xr_probe.py [--frames N] [--runtime PATH_TO_runtime.json] [--json] [--show]

--runtime sets XR_RUNTIME_JSON for THIS PROCESS ONLY, so the machine-wide runtime
(Virtual Desktop, SteamVR, Quest Link) is never touched.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

# Extensions our stereo work is likely to lean on. Missing ones are reported, not fatal -
# the probe's job is to state exactly what a runtime does and does not have.
WANTED_EXTENSIONS = [
    "XR_KHR_composition_layer_depth",
    "XR_KHR_win32_convert_performance_counter_time",
    "XR_KHR_D3D11_enable",
    "XR_KHR_D3D12_enable",
    "XR_KHR_opengl_enable",
    "XR_KHR_vulkan_enable2",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=30)
    ap.add_argument("--runtime", default=None,
                    help="path to an OpenXR runtime .json; sets XR_RUNTIME_JSON for this process only")
    ap.add_argument("--json", action="store_true", help="emit machine-readable results")
    ap.add_argument("--show", action="store_true", help="show the probe's own GL window too")
    args = ap.parse_args()

    if args.runtime:
        runtime = os.path.abspath(args.runtime)
        if not os.path.isfile(runtime):
            print(f"FAIL: runtime manifest not found: {runtime}")
            return 1
        os.environ["XR_RUNTIME_JSON"] = runtime

    report: dict = {"runtime_json": os.environ.get("XR_RUNTIME_JSON", "<machine default>"),
                    "frames_requested": args.frames}
    try:
        _probe(args, report)
    except BaseException as exc:  # noqa: BLE001 - the probe reports, it does not handle
        report["error"] = f"{type(exc).__name__}: {exc}"

    ok = (report.get("view_count") == 2
          and report.get("frames_submitted", 0) >= args.frames
          and "error" not in report)
    report["verdict"] = "PASS" if ok else "FAIL"
    _emit(report, args.json)
    return 0 if ok else 1


def _probe(args, report: dict) -> None:
    import glfw
    import xr
    from OpenGL import GL, WGL

    # --- 1. what the loader found -------------------------------------------------
    available = {_s(e.extension_name) for e in xr.enumerate_instance_extension_properties()}
    report["extension_count"] = len(available)
    report["extensions_present"] = sorted(x for x in WANTED_EXTENSIONS if x in available)
    report["extensions_missing"] = sorted(x for x in WANTED_EXTENSIONS if x not in available)

    if xr.KHR_OPENGL_ENABLE_EXTENSION_NAME not in available:
        raise RuntimeError("runtime has no XR_KHR_opengl_enable; this probe needs the GL path")

    # --- 2. instance, system, view configuration ----------------------------------
    instance = xr.create_instance(xr.InstanceCreateInfo(
        enabled_extension_names=[xr.KHR_OPENGL_ENABLE_EXTENSION_NAME]))
    props = xr.get_instance_properties(instance)
    report["runtime_name"] = _s(props.runtime_name)
    report["runtime_version"] = str(props.runtime_version)

    system_id = xr.get_system(instance, xr.SystemGetInfo(
        form_factor=xr.FormFactor.HEAD_MOUNTED_DISPLAY))
    report["system_name"] = _s(xr.get_system_properties(instance, system_id).system_name)

    cfg = xr.ViewConfigurationType.PRIMARY_STEREO
    views_cfg = xr.enumerate_view_configuration_views(instance, system_id, cfg)
    report["view_count"] = len(views_cfg)
    report["per_eye_recommended"] = [[c.recommended_image_rect_width,
                                      c.recommended_image_rect_height] for c in views_cfg]
    report["per_eye_max"] = [[c.max_image_rect_width, c.max_image_rect_height] for c in views_cfg]
    report["recommended_swapchain_samples"] = [c.recommended_swapchain_sample_count for c in views_cfg]

    # The runtime insists this is called before xrCreateSession on the GL path.
    xr.get_opengl_graphics_requirements_khr(instance, system_id)

    # --- 3. a real GL context for the session -------------------------------------
    if not glfw.init():
        raise RuntimeError("glfw.init() failed")
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 4)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 5)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
    glfw.window_hint(glfw.VISIBLE, glfw.TRUE if args.show else glfw.FALSE)
    w, h = report["per_eye_recommended"][0]
    window = glfw.create_window(max(w // 2, 320), max(h // 2, 240), "xr_probe", None, None)
    if not window:
        raise RuntimeError("glfw.create_window() failed")
    glfw.make_context_current(window)

    import ctypes
    binding = xr.GraphicsBindingOpenGLWin32KHR(  # must outlive create_session
        h_dc=WGL.wglGetCurrentDC(), h_glrc=WGL.wglGetCurrentContext())
    session = xr.create_session(instance, xr.SessionCreateInfo(
        system_id=system_id,
        next=ctypes.cast(ctypes.pointer(binding), ctypes.c_void_p)))
    space = xr.create_reference_space(session, xr.ReferenceSpaceCreateInfo(
        reference_space_type=xr.ReferenceSpaceType.STAGE))

    # --- 4. swapchains, one per eye ----------------------------------------------
    formats = xr.enumerate_swapchain_formats(session)
    GL_SRGB8_ALPHA8 = 0x8C43
    fmt = GL_SRGB8_ALPHA8 if GL_SRGB8_ALPHA8 in formats else formats[0]
    report["swapchain_format"] = hex(fmt)
    report["swapchain_format_srgb"] = fmt == GL_SRGB8_ALPHA8

    swapchains, images, rects = [], [], []
    for c in views_cfg:
        sc = xr.create_swapchain(session, xr.SwapchainCreateInfo(
            usage_flags=xr.SwapchainUsageFlags.COLOR_ATTACHMENT_BIT,
            format=fmt, sample_count=1,
            width=c.recommended_image_rect_width, height=c.recommended_image_rect_height,
            face_count=1, array_size=1, mip_count=1))
        swapchains.append(sc)
        images.append(xr.enumerate_swapchain_images(sc, xr.SwapchainImageOpenGLKHR))
        rects.append(xr.Rect2Di(xr.Offset2Di(0, 0), xr.Extent2Di(
            c.recommended_image_rect_width, c.recommended_image_rect_height)))

    fbo = GL.glGenFramebuffers(1)

    # --- 5. the frame loop --------------------------------------------------------
    from xr.utils import SessionStateManager
    mgr = SessionStateManager(instance, session, cfg)
    rendered, waited, fovs, poses = 0, 0, [], []
    frame_ms: list[float] = []
    t0 = time.perf_counter()
    deadline = t0 + 60.0
    try:
        while rendered < args.frames and time.perf_counter() < deadline:
            glfw.poll_events()
            while True:
                try:
                    mgr.handle_xr_event(xr.poll_event(instance))
                except xr.EventUnavailable:
                    break
            fs = mgr.begin_frame()
            if fs is None:
                waited += 1
                time.sleep(0.005)
                continue
            t_frame = time.perf_counter()
            layers = []
            if fs.should_render:
                _, view_list = xr.locate_views(session, xr.ViewLocateInfo(
                    view_configuration_type=cfg, display_time=fs.predicted_display_time, space=space))
                projs = []
                for eye, view in enumerate(view_list):
                    if rendered == 0:
                        f, p = view.fov, view.pose.position
                        fovs.append([round(x, 5) for x in
                                     (f.angle_left, f.angle_right, f.angle_up, f.angle_down)])
                        poses.append([round(x, 5) for x in (p.x, p.y, p.z)])
                    idx = xr.acquire_swapchain_image(swapchains[eye], xr.SwapchainImageAcquireInfo())
                    xr.wait_swapchain_image(swapchains[eye],
                                            xr.SwapchainImageWaitInfo(timeout=xr.INFINITE_DURATION))
                    GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, fbo)
                    GL.glFramebufferTexture2D(GL.GL_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0,
                                              GL.GL_TEXTURE_2D, images[eye][idx].image, 0)
                    # Distinct per-eye colours: a stereo capture that shows one colour in
                    # both panes means the eyes are not actually separate.
                    GL.glClearColor(*((0.15, 0.0, 0.35, 1.0) if eye == 0 else (0.0, 0.3, 0.15, 1.0)))
                    GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
                    GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, 0)
                    xr.release_swapchain_image(swapchains[eye], xr.SwapchainImageReleaseInfo())
                    projs.append(xr.CompositionLayerProjectionView(
                        pose=view.pose, fov=view.fov,
                        sub_image=xr.SwapchainSubImage(
                            swapchain=swapchains[eye], image_rect=rects[eye], image_array_index=0)))
                layer = xr.CompositionLayerProjection(space=space, views=projs)
                layers = [ctypes_ref(layer)]
            xr.end_frame(session, xr.FrameEndInfo(
                display_time=fs.predicted_display_time,
                environment_blend_mode=xr.EnvironmentBlendMode.OPAQUE,
                layers=layers))
            frame_ms.append((time.perf_counter() - t_frame) * 1000.0)
            rendered += 1
    except SessionStateManager.ExitRenderLoop:
        report["note"] = "runtime asked the session to exit before the frame count was reached"
    elapsed = time.perf_counter() - t0

    report["frames_submitted"] = rendered
    report["idle_polls_before_ready"] = waited
    report["seconds"] = round(elapsed, 3)
    report["fps"] = round(rendered / elapsed, 1) if elapsed > 0 else None
    if frame_ms:
        s = sorted(frame_ms)
        report["frame_ms_p50"] = round(s[len(s) // 2], 3)
        report["frame_ms_p95"] = round(s[int(len(s) * 0.95) - 1 if len(s) > 1 else 0], 3)
    report["per_eye_fov_rad"] = fovs
    report["per_eye_pose_m"] = poses
    if len(poses) == 2:
        report["ipd_m"] = round(abs(poses[1][0] - poses[0][0]), 5)

    # --- 6. tidy up ---------------------------------------------------------------
    for sc in swapchains:
        xr.destroy_swapchain(sc)
    xr.destroy_space(space)
    xr.destroy_session(session)
    xr.destroy_instance(instance)
    glfw.destroy_window(window)
    glfw.terminate()


def ctypes_ref(layer):
    import ctypes
    import xr
    return ctypes.cast(ctypes.byref(layer), ctypes.POINTER(xr.CompositionLayerBaseHeader))


def _s(value) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


def _emit(report: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, indent=2))
        return
    print(f"runtime manifest : {report['runtime_json']}")
    print(f"runtime          : {report.get('runtime_name', '?')} {report.get('runtime_version', '')}")
    print(f"system           : {report.get('system_name', '?')}")
    print(f"extensions       : {report.get('extension_count', 0)} advertised")
    for e in report.get("extensions_present", []):
        print(f"   present       {e}")
    for e in report.get("extensions_missing", []):
        print(f"   MISSING       {e}")
    print(f"stereo views     : {report.get('view_count', '?')}")
    for i, r in enumerate(report.get("per_eye_recommended", [])):
        print(f"   eye {i} target  {r[0]} x {r[1]} recommended")
    for i, f in enumerate(report.get("per_eye_fov_rad", [])):
        print(f"   eye {i} fov     L{f[0]:+.4f} R{f[1]:+.4f} U{f[2]:+.4f} D{f[3]:+.4f} rad")
    for i, p in enumerate(report.get("per_eye_pose_m", [])):
        print(f"   eye {i} pos     x{p[0]:+.4f} y{p[1]:+.4f} z{p[2]:+.4f} m")
    if "ipd_m" in report:
        print(f"   eye separation {report['ipd_m'] * 1000:.1f} mm")
    if "swapchain_format" in report:
        print(f"swapchain format : {report['swapchain_format']}"
              f"{' (sRGB)' if report.get('swapchain_format_srgb') else ''}")
    print(f"frames           : {report.get('frames_submitted', 0)}/{report.get('frames_requested', '?')}"
          f" in {report.get('seconds', 0)}s ({report.get('fps', '?')} fps)")
    if "frame_ms_p50" in report:
        print(f"   frame time    p50 {report['frame_ms_p50']} ms  p95 {report['frame_ms_p95']} ms")
    if "note" in report:
        print(f"note             : {report['note']}")
    if "error" in report:
        print(f"ERROR            : {report['error']}")
    print(f"VERDICT          : {report.get('verdict', 'FAIL')}")


if __name__ == "__main__":
    sys.exit(main())

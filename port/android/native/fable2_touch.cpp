// SPDX-License-Identifier: GPL-3.0-or-later
// SDL3 virtual joystick for Fable II Android touchscreen controls.
// Adapted from the architecture of Xerenge's Android SDL virtual gamepad.
// The SDL input driver sees the injected pad just like a physical controller.
// License note: if deriving from Xerenge source, comply with GPL-3.0-or-later.
#include <jni.h>
#include <SDL3/SDL.h>
#include <mutex>

namespace {
std::mutex touch_mutex;
SDL_Joystick* touch_pad = nullptr;

SDL_Joystick* get_pad() {
    if (touch_pad) return touch_pad;
    if (!(SDL_WasInit(SDL_INIT_JOYSTICK) & SDL_INIT_JOYSTICK)) return nullptr;
    SDL_VirtualJoystickDesc description;
    SDL_INIT_INTERFACE(&description);
    description.type = SDL_JOYSTICK_TYPE_GAMEPAD;
    description.naxes = SDL_GAMEPAD_AXIS_COUNT;
    description.nbuttons = SDL_GAMEPAD_BUTTON_DPAD_RIGHT + 1;
    description.axis_mask = (1u << SDL_GAMEPAD_AXIS_COUNT) - 1;
    description.button_mask = (1u << (SDL_GAMEPAD_BUTTON_DPAD_RIGHT + 1)) - 1;
    description.name = "Fable II virtual touch pad";
    SDL_JoystickID id = SDL_AttachVirtualJoystick(&description);
    if (!id) return nullptr;
    touch_pad = SDL_OpenJoystick(id);
    return touch_pad;
}
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_nanaveone_fable2_Fable2TouchControls_nativeAttach(JNIEnv*, jclass) {
    std::lock_guard<std::mutex> lock(touch_mutex);
    return get_pad() != nullptr;
}

extern "C" JNIEXPORT void JNICALL
Java_com_nanaveone_fable2_Fable2TouchControls_nativeButton(
        JNIEnv*, jclass, jint button, jboolean pressed) {
    if (button < 0 || button > SDL_GAMEPAD_BUTTON_DPAD_RIGHT) return;
    std::lock_guard<std::mutex> lock(touch_mutex);
    if (SDL_Joystick* pad = get_pad()) {
        SDL_SetJoystickVirtualButton(pad, button, pressed);
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_nanaveone_fable2_Fable2TouchControls_nativeAxis(
        JNIEnv*, jclass, jint axis, jfloat value) {
    if (axis < 0 || axis >= SDL_GAMEPAD_AXIS_COUNT) return;
    std::lock_guard<std::mutex> lock(touch_mutex);
    if (SDL_Joystick* pad = get_pad()) {
        const bool trigger = (axis == SDL_GAMEPAD_AXIS_LEFT_TRIGGER ||
                              axis == SDL_GAMEPAD_AXIS_RIGHT_TRIGGER);
        const float bounded = SDL_clamp(value, trigger ? 0.0f : -1.0f, 1.0f);
        const float raw = trigger ?
            (float(SDL_JOYSTICK_AXIS_MIN) + bounded *
              float(SDL_JOYSTICK_AXIS_MAX - SDL_JOYSTICK_AXIS_MIN)) :
            (bounded * float(SDL_JOYSTICK_AXIS_MAX));
        SDL_SetJoystickVirtualAxis(pad, axis, Sint16(raw));
    }
}

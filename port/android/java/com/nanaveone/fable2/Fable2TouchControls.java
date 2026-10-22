// SPDX-License-Identifier: GPL-3.0-or-later
package com.nanaveone.fable2;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.util.SparseArray;
import android.view.MotionEvent;
import android.view.View;

/**
 * A lightweight multipointer virtual Xbox gamepad. Sends events through
 * SDL3's virtual joystick API; NOT an emulator of Xbox input protocols.
 * Can be hidden when a physical controller is preferred.
 */
public final class Fable2TouchControls extends View {
    private static native boolean nativeAttach();
    private static native void nativeButton(int button, boolean pressed);
    private static native void nativeAxis(int axis, float value);

    private static final int STICK_LEFT = 0;
    private static final int STICK_RIGHT = 1;
    private static final int BUTTON_A = 0, BUTTON_B = 1, BUTTON_X = 2, BUTTON_Y = 3;
    private static final int BUTTON_BACK = 4, BUTTON_START = 6;
    private static final int BUTTON_LB = 9, BUTTON_RB = 10;
    private static final int DPAD_UP = 11, DPAD_DOWN = 12, DPAD_LEFT = 13, DPAD_RIGHT = 14;
    private static final int AXIS_LX = 0, AXIS_LY = 1, AXIS_RX = 2, AXIS_RY = 3;
    private static final int AXIS_LT = 4, AXIS_RT = 5;

    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final SparseArray<PadControl> held = new SparseArray<>();
    private final PadControl[] controls = {
        new PadControl("L", .17f, .71f, .115f, -1, STICK_LEFT, -1),
        new PadControl("R", .66f, .78f, .092f, -1, STICK_RIGHT, -1),
        new PadControl("A", .89f, .60f, .060f, BUTTON_A, -1, -1),
        new PadControl("B", .96f, .50f, .055f, BUTTON_B, -1, -1),
        new PadControl("X", .82f, .50f, .055f, BUTTON_X, -1, -1),
        new PadControl("Y", .89f, .40f, .055f, BUTTON_Y, -1, -1),
        new PadControl("LB", .20f, .17f, .070f, BUTTON_LB, -1, -1),
        new PadControl("RB", .79f, .17f, .070f, BUTTON_RB, -1, -1),
        new PadControl("LT", .08f, .32f, .065f, -1, -1, AXIS_LT),
        new PadControl("RT", .92f, .32f, .065f, -1, -1, AXIS_RT),
        new PadControl("◀", .31f, .83f, .048f, DPAD_LEFT, -1, -1),
        new PadControl("▶", .43f, .83f, .048f, DPAD_RIGHT, -1, -1),
        new PadControl("▲", .37f, .73f, .048f, DPAD_UP, -1, -1),
        new PadControl("▼", .37f, .93f, .048f, DPAD_DOWN, -1, -1),
        new PadControl("View", .42f, .14f, .053f, BUTTON_BACK, -1, -1),
        new PadControl("Menu", .58f, .14f, .053f, BUTTON_START, -1, -1),
    };

    private static final class PadControl {
        final String label;
        final float x, y, size;
        final int button, stick, trigger;
        int pointer = -1;
        PadControl(String label, float x, float y, float size,
                   int button, int stick, int trigger) {
            this.label = label;
            this.x = x;
            this.y = y;
            this.size = size;
            this.button = button;
            this.stick = stick;
            this.trigger = trigger;
        }
        float px(int width) { return x * width; }
        float py(int height) { return y * height; }
        float radius(int width, int height) { return size * Math.min(width, height); }
    }

    public Fable2TouchControls(Context context) {
        super(context);
        setFocusable(false);
        try { nativeAttach(); } catch (UnsatisfiedLinkError ignored) {
            // The runtime loads the lib in SDLActivity; re-attempt on input.
        }
    }

    @Override
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        for (PadControl control : controls) {
            float cx = control.px(getWidth()), cy = control.py(getHeight());
            float radius = control.radius(getWidth(), getHeight());
            paint.setColor(control.pointer >= 0 ? Color.argb(150, 45, 135, 210)
                    : Color.argb(105, 15, 30, 45));
            paint.setStyle(Paint.Style.FILL);
            canvas.drawCircle(cx, cy, radius, paint);
            paint.setColor(Color.argb(195, 240, 245, 255));
            paint.setStyle(Paint.Style.STROKE);
            paint.setStrokeWidth(2 * getResources().getDisplayMetrics().density);
            canvas.drawCircle(cx, cy, radius, paint);
            paint.setStyle(Paint.Style.FILL);
            paint.setTextSize(Math.max(13, radius * .47f));
            paint.setTextAlign(Paint.Align.CENTER);
            Paint.FontMetrics metrics = paint.getFontMetrics();
            canvas.drawText(control.label, cx, cy - (metrics.ascent + metrics.descent) / 2f, paint);
        }
    }

    @Override
    public boolean onTouchEvent(MotionEvent event) {
        int action = event.getActionMasked();
        int index = event.getActionIndex();
        if (action == MotionEvent.ACTION_DOWN || action == MotionEvent.ACTION_POINTER_DOWN) {
            int id = event.getPointerId(index);
            float x = event.getX(index), y = event.getY(index);
            PadControl chosen = null;
            for (PadControl control : controls) {
                if (control.pointer != -1) continue;
                float dx = x - control.px(getWidth());
                float dy = y - control.py(getHeight());
                float radius = control.radius(getWidth(), getHeight()) * 1.25f;
                if (dx * dx + dy * dy <= radius * radius) { chosen = control; break; }
            }
            if (chosen != null) {
                chosen.pointer = id;
                held.put(id, chosen);
                updateControl(chosen, x, y, true);
            }
        } else if (action == MotionEvent.ACTION_MOVE) {
            for (int i = 0; i < event.getPointerCount(); ++i) {
                PadControl control = held.get(event.getPointerId(i));
                if (control != null && control.stick >= 0)
                    updateControl(control, event.getX(i), event.getY(i), true);
            }
        } else if (action == MotionEvent.ACTION_UP || action == MotionEvent.ACTION_POINTER_UP) {
            int id = event.getPointerId(index);
            PadControl control = held.get(id);
            if (control != null) {
                updateControl(control, 0, 0, false);
                control.pointer = -1;
                held.remove(id);
            }
        } else if (action == MotionEvent.ACTION_CANCEL) {
            releaseAll();
        }
        invalidate();
        return true;
    }

    private void updateControl(PadControl control, float x, float y, boolean pressed) {
        if (control.button >= 0) {
            nativeButton(control.button, pressed);
        } else if (control.trigger >= 0) {
            nativeAxis(control.trigger, pressed ? 1f : 0f);
        } else if (control.stick >= 0) {
            int axisX = control.stick == STICK_LEFT ? AXIS_LX : AXIS_RX;
            int axisY = control.stick == STICK_LEFT ? AXIS_LY : AXIS_RY;
            float radius = Math.max(1, control.radius(getWidth(), getHeight()));
            float vx = pressed ? (x - control.px(getWidth())) / radius : 0f;
            float vy = pressed ? (y - control.py(getHeight())) / radius : 0f;
            float length = (float) Math.hypot(vx, vy);
            if (length > 1) { vx /= length; vy /= length; }
            nativeAxis(axisX, vx);
            nativeAxis(axisY, vy);
        }
    }

    public void releaseAll() {
        for (int i = 0; i < held.size(); i++) {
            PadControl control = held.valueAt(i);
            updateControl(control, 0, 0, false);
            control.pointer = -1;
        }
        held.clear();
        invalidate();
    }

    @Override
    protected void onDetachedFromWindow() {
        releaseAll();
        super.onDetachedFromWindow();
    }
}

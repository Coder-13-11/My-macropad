"""CircuitPython firmware for mixu's macropad

Wiring:
- Buttons: D0, D1, D7
- Encoder A/B: D2, D3
- Encoder click: D6
- OLED: SDA=D4, SCL=D5, addr=0x3C
- NeoPixel data: D10
"""

import time
import board
import busio
import digitalio
import neopixel
import usb_hid

import adafruit_ssd1306
from rotaryio import IncrementalEncoder
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode
from adafruit_hid.consumer_control import ConsumerControl
from adafruit_hid.consumer_control_code import ConsumerControlCode


# Pin config
KEY_PINS = (board.D0, board.D1, board.D7)
ENC_A = board.D2
ENC_B = board.D3
ENC_SW = board.D6
I2C_SDA = board.D4
I2C_SCL = board.D5
LED_PIN = board.D10
LED_COUNT = 1

# Responsiveness tuning
DISPLAY_REFRESH_INTERVAL = 0.02  # 50 Hz
MAIN_LOOP_SLEEP = 0.002
BUTTON_DEBOUNCE = 0.01
ENCODER_SWITCH_DEBOUNCE = 0.03
LAYER_FLASH_DURATION = 0.5
LAYER_FLASH_SOLID_TIME = 0.14


# HID devices
kbd = Keyboard(usb_hid.devices)
consumer = ConsumerControl(usb_hid.devices)


class Button:
    def __init__(self, pin, debounce=BUTTON_DEBOUNCE):
        self.pin = digitalio.DigitalInOut(pin)
        self.pin.direction = digitalio.Direction.INPUT
        self.pin.pull = digitalio.Pull.UP
        self.debounce = debounce
        self._last_state = self.pin.value
        self._last_change = time.monotonic()

    def fell(self):
        now = time.monotonic()
        state = self.pin.value
        if state != self._last_state and (now - self._last_change) >= self.debounce:
            self._last_state = state
            self._last_change = now
            return not state
        return False

    def is_pressed(self):
        return not self.pin.value


def send_combo(*keys):
    for key in keys:
        kbd.press(key)
    kbd.release_all()


def act_prev_track():
    consumer.send(ConsumerControlCode.SCAN_PREVIOUS_TRACK)


def act_play_pause():
    consumer.send(ConsumerControlCode.PLAY_PAUSE)


def act_next_track():
    consumer.send(ConsumerControlCode.SCAN_NEXT_TRACK)


def act_copy():
    send_combo(Keycode.CONTROL, Keycode.C)


def act_paste():
    send_combo(Keycode.CONTROL, Keycode.V)


def act_undo():
    send_combo(Keycode.CONTROL, Keycode.Z)


BUTTON_LAYERS = (
    (act_prev_track, act_play_pause, act_next_track),
    (act_copy, act_paste, act_undo),
)

ACTION_LABELS = (
    ("Previous Track", "Play/Pause", "Next Track"),
    ("Copy", "Paste", "Undo"),
)

BUTTON_DISPLAY_LABELS = (
    ("prev", "play", "next"),
    ("copy", "paste", "undo"),
)


def update_leds(pixels, layer):
    # Layer color feedback: green for layer 0, blue for layer 1.
    pixels.fill((0, 32, 0) if layer == 0 else (0, 0, 32))
    pixels.show()


def update_display(display, layer, now, volume_until, volume_direction, pressed_states, layer_flash_start, layer_flash_until):
    if display is None:
        return

    display.fill(0)

    # Top title
    display.text("mixu's macropad", 0, 0, 1)

    # Layer indicator (top-right): white text on black; flash background on layer change.
    layer_x = 121
    layer_y = 1
    layer_text = str(layer)
    layer_text_color = 1
    if now < layer_flash_until:
        elapsed = now - layer_flash_start
        should_show_bg = elapsed < LAYER_FLASH_SOLID_TIME or int(elapsed * 18) % 2 == 0
        if should_show_bg:
            display.fill_rect(119, 0, 9, 9, 1)
            layer_text_color = 0
    display.text(layer_text, layer_x, layer_y, layer_text_color)

    # Center area: show current volume action while rotating knob.
    if now < volume_until:
        volume_text = "VOL +" if volume_direction > 0 else "VOL -"
        display.fill_rect(43, 11, 35, 10, 1)
        display.text(volume_text, 46, 12, 0)

    # Bottom row: current layer key labels, highlight currently pressed key.
    labels = BUTTON_DISPLAY_LABELS[layer]
    box_y = 22
    box_h = 10
    box_w = 42
    for idx, label in enumerate(labels):
        box_x = idx * (box_w + 1)
        is_highlighted = pressed_states[idx]
        if is_highlighted:
            display.fill_rect(box_x, box_y, box_w, box_h, 1)
            text_color = 0
        else:
            text_color = 1
        text_x = box_x + max(1, (box_w - (len(label) * 6)) // 2)
        display.text(label, text_x, 23, text_color)

    display.show()


def boot_animation(display):
    if display is None:
        return

    # Wake-up animation: fill cube tiles in a spiral from the top edge inward.
    tile = 8
    cols = 128 // tile
    rows = 32 // tile
    left = 0
    right = cols - 1
    top = 0
    bottom = rows - 1

    display.fill(0)
    display.show()

    while left <= right and top <= bottom:
        for col in range(left, right + 1):
            display.fill_rect(col * tile, top * tile, tile, tile, 1)
            display.show()
            time.sleep(0.02)
        top += 1

        for row in range(top, bottom + 1):
            display.fill_rect(right * tile, row * tile, tile, tile, 1)
            display.show()
            time.sleep(0.02)
        right -= 1

        if top <= bottom:
            for col in range(right, left - 1, -1):
                display.fill_rect(col * tile, bottom * tile, tile, tile, 1)
                display.show()
                time.sleep(0.02)
            bottom -= 1

        if left <= right:
            for row in range(bottom, top - 1, -1):
                display.fill_rect(left * tile, row * tile, tile, tile, 1)
                display.show()
                time.sleep(0.02)
            left += 1

    display.fill(0)
    display.rect(0, 0, 128, 32, 1)
    display.show()
    display.text("Welcome", 44, 7, 1)
    display.show()
    time.sleep(1.5)
    display.text("mixu", 53, 18, 1)
    display.show()
    time.sleep(1)
    
    # Invert
    for _ in range(4):
        time.sleep(0.3)
        display.invert(True)
        time.sleep(0.3)
        display.invert(False)


    display.fill(0)
    display.show()
    time.sleep(0.5)


def main():
    print("Starting macropad firmware")

    buttons = [Button(pin) for pin in KEY_PINS]
    encoder = IncrementalEncoder(ENC_A, ENC_B)
    last_encoder_pos = encoder.position

    enc_switch = Button(ENC_SW, debounce=ENCODER_SWITCH_DEBOUNCE)

    pixels = neopixel.NeoPixel(LED_PIN, LED_COUNT, brightness=0.2, auto_write=False)

    display = None
    try:
        i2c = busio.I2C(I2C_SCL, I2C_SDA)
        display = adafruit_ssd1306.SSD1306_I2C(128, 32, i2c, addr=0x3C)
        boot_animation(display)
    except Exception as err:
        print("Display init failed:", err)

    layer = 0
    volume_until = 0.0
    volume_direction = 1
    layer_flash_start = 0.0
    layer_flash_until = 0.0
    last_display_update = 0.0

    update_leds(pixels, layer)
    update_display(
        display,
        layer,
        time.monotonic(),
        volume_until,
        volume_direction,
        [False, False, False],
        layer_flash_start,
        layer_flash_until,
    )

    while True:
        now = time.monotonic()

        # Buttons
        for idx, button in enumerate(buttons):
            if button.fell():
                try:
                    BUTTON_LAYERS[layer][idx]()
                except Exception as err:
                    print("Button action failed:", err)

        # Encoder rotate
        current_pos = encoder.position
        if current_pos != last_encoder_pos:
            diff = current_pos - last_encoder_pos
            if diff > 0:
                consumer.send(ConsumerControlCode.VOLUME_INCREMENT)
                volume_direction = 1
            else:
                consumer.send(ConsumerControlCode.VOLUME_DECREMENT)
                volume_direction = -1
            volume_until = now + 1.2
            last_encoder_pos = current_pos

        # Encoder click toggles layer
        if enc_switch.fell():
            now_click = now
            layer = 1 - layer
            layer_flash_start = now_click
            layer_flash_until = now_click + LAYER_FLASH_DURATION
            update_leds(pixels, layer)
            # Push one immediate frame so very fast clicks still show flash feedback.
            pressed_states = [button.is_pressed() for button in buttons]
            update_display(
                display,
                layer,
                now_click,
                volume_until,
                volume_direction,
                pressed_states,
                layer_flash_start,
                layer_flash_until,
            )
            last_display_update = now_click

        # OLED refresh
        if now - last_display_update >= DISPLAY_REFRESH_INTERVAL:
            pressed_states = [button.is_pressed() for button in buttons]
            update_display(
                display,
                layer,
                now,
                volume_until,
                volume_direction,
                pressed_states,
                layer_flash_start,
                layer_flash_until,
            )
            last_display_update = now

        time.sleep(MAIN_LOOP_SLEEP)


if __name__ == "__main__":
    main()
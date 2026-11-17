# -*- coding: utf-8 -*-
"""
GHOST MOUSE - Control del cursor de Windows con la mano (webcam)
================================================================
Dependencias:  pip install -U opencv-python mediapipe

Gestos (mano frente a la cámara):
  - Mover cursor ..... mueve la mano (se sigue el nudillo del índice, muy estable)
  - Clic izquierdo ... juntar PULGAR + ÍNDICE (pellizco corto = clic,
                       pellizco mantenido = arrastrar)
  - Clic derecho ..... juntar PULGAR + DEDO MEDIO (un toque = un clic)
  - SCROLL ........... PUÑO CERRADO + mover la mano. Estilo pantalla táctil:
                         mano hacia ABAJO  -> la página sube (scroll arriba)
                         mano hacia ARRIBA -> la página baja (scroll abajo)
                       Mientras haces scroll el cursor se queda quieto.
  - ALT+TAB .......... CUERNITOS (indice y menique estirados, medio y anular
                       doblados) mantenidos ~0.2 s. Cambia a la ventana anterior.
                       Mientras haces la pose el cursor se queda quieto.

Teclas globales (funcionan aunque otra ventana tenga el foco):
  - F8 : pausar / reanudar el control
  - F9 : salir

NOTA: MediaPipe >= 0.10.30 eliminó la API antigua (mp.solutions). Este código
usa la API nueva "Tasks" (HandLandmarker). La primera vez que se ejecuta
descarga el modelo hand_landmarker.task (~7 MB) junto al script.
"""

import ctypes
import math
import os
import sys
import time
import urllib.request
from threading import Thread

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

if sys.platform != "win32":
    sys.exit("Ghost Mouse está pensado para Windows.")

_tracking_thread = None
_tracking_stop_requested = False

# ============================================================================
# CONFIGURACIÓN (ajusta aquí sin tocar el resto del código)
# ============================================================================
CAM_INDEX = 0
CAM_WIDTH, CAM_HEIGHT = 320, 240
CAM_FPS = 30

PROCESS_EVERY_N = 1
IDLE_EVERY_N = 4
IDLE_AFTER_SEC = 2.0

POINTER_LANDMARK = 5          # 5 = nudillo del índice; 8 = punta del índice

MARGIN_X = 0.20
MARGIN_TOP = 0.20
MARGIN_BOTTOM = 0.30

MIN_ALPHA = 0.55
MAX_ALPHA = 0.98
SPEED_REF_PX = 140
DEAD_ZONE_PX = 0.5

PINCH_ON = 0.30
PINCH_OFF = 0.45
PINCH_FRAMES_ON = 2
RIGHT_CLICK_COOLDOWN = 0.60

# --- Scroll con puño cerrado ------------------------------------------------
SCROLL_FRAMES_ON = 3          # Frames seguidos con el puño cerrado para activar el scroll
SCROLL_GAIN = 900             # Sensibilidad: unidades de rueda por "tamaño de mano" recorrido
                              # (120 unidades = 1 "tick" de la rueda). Sube = más rápido.
SCROLL_DEAD_ZONE = 0.008      # Movimiento mínimo (fracción del tamaño de mano) que cuenta
SCROLL_SMOOTH = 0.5           # 0..1 (más alto = responde más rápido, menos suave)
SCROLL_INVERT = False         # True = invierte la dirección (scroll "clásico" de ratón)
FIST_RATIO = 1.20             # Puño: las 4 puntas deben estar a menos de FIST_RATIO * tamaño de mano
                              # de la muñeca (mano abierta ~1.9, puño ~1.0). Sube si no detecta el puño.

# --- Alt+Tab con cuernitos --------------------------------------------------
ALTTAB_FRAMES_ON = 6          # Frames seguidos con la pose para disparar (~0.2 s a 30 fps)
ALTTAB_COOLDOWN = 1.0         # Segundos mínimos entre un Alt+Tab y otro
FINGER_EXT_RATIO = 1.15       # Punta / articulación media (respecto a la muñeca) para considerar el dedo estirado
                              # Si no detecta los cuernitos, bájalo a 1.05-1.10

SHOW_PREVIEW = False          # True = ventana de depuración. Salir: tecla 'q'

# --- Modelo -----------------------------------------------------------------
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
             "hand_landmarker/float16/latest/hand_landmarker.task")
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hand_landmarker.task")

# Conexiones de la mano (para la previsualización; la API nueva ya no trae drawing_utils)
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20), (0, 17),
]

VK_F8, VK_F9 = 0x77, 0x78
VK_MENU, VK_TAB = 0x12, 0x09   # Alt y Tab
KEYEVENTF_KEYUP = 0x0002

# ============================================================================
# API DE WINDOWS (ctypes)
# ============================================================================
user32 = ctypes.windll.user32
user32.SetProcessDPIAware()
SCREEN_W = user32.GetSystemMetrics(0)
SCREEN_H = user32.GetSystemMetrics(1)

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800


class Mouse:
    """Envoltorio mínimo para mover el cursor, pulsar botones y usar la rueda."""

    def __init__(self):
        self.left_is_down = False
        self._last_pos = (-1, -1)

    def move(self, x, y):
        pos = (int(x), int(y))
        if pos != self._last_pos:
            user32.SetCursorPos(*pos)
            self._last_pos = pos

    def left_down(self):
        if not self.left_is_down:
            user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            self.left_is_down = True

    def left_up(self):
        if self.left_is_down:
            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            self.left_is_down = False

    @staticmethod
    def right_click():
        user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
        user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)

    @staticmethod
    def wheel(amount):
        """amount > 0 = scroll hacia arriba, < 0 = hacia abajo (120 = un tick)."""
        user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, int(amount), 0)

    @staticmethod
    def alt_tab():
        """Alt+Tab rápido: cambia a la ventana anterior."""
        user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.keybd_event(VK_TAB, 0, 0, 0)
        user32.keybd_event(VK_TAB, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.05)
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)


class Hotkey:
    """Detecta la pulsación (flanco de subida) de una tecla global."""

    def __init__(self, vk):
        self.vk = vk
        self._prev = False

    def pressed(self):
        down = bool(user32.GetAsyncKeyState(self.vk) & 0x8000)
        edge = down and not self._prev
        self._prev = down
        return edge


# ============================================================================
# LÓGICA DE SUAVIZADO Y GESTOS
# ============================================================================
class CursorSmoother:
    """Media móvil exponencial adaptativa + zona muerta."""

    def __init__(self):
        self.x = None
        self.y = None

    def reset(self):
        self.x = self.y = None

    def update(self, tx, ty):
        if self.x is None:
            self.x, self.y = tx, ty
            return self.x, self.y
        dist = math.hypot(tx - self.x, ty - self.y)
        if dist < DEAD_ZONE_PX:
            return self.x, self.y
        alpha = MIN_ALPHA + (MAX_ALPHA - MIN_ALPHA) * min(dist / SPEED_REF_PX, 1.0)
        self.x += (tx - self.x) * alpha
        self.y += (ty - self.y) * alpha
        return self.x, self.y


class PinchDetector:
    """Estado de un pellizco con histéresis y antirrebote."""

    def __init__(self):
        self.active = False
        self._count = 0

    def reset(self):
        self.active = False
        self._count = 0

    def update(self, ratio):
        if ratio is None:
            self.reset()
        elif self.active:
            if ratio > PINCH_OFF:
                self.active = False
                self._count = 0
        else:
            if ratio < PINCH_ON:
                self._count += 1
                if self._count >= PINCH_FRAMES_ON:
                    self.active = True
            else:
                self._count = 0
        return self.active


class ScrollGesture:
    """Scroll con índice + medio (estilo pantalla táctil)."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.count = 0          # Frames consecutivos con la pose correcta
        self.active = False
        self._prev_y = None
        self._vel = 0.0
        self._accum = 0.0

    def update(self, pose_ok, y_norm):
        """y_norm: posición vertical de los dedos / tamaño de mano. Devuelve unidades de rueda."""
        if not pose_ok:
            self.reset()
            return 0
        self.count += 1
        if self.count < SCROLL_FRAMES_ON:
            self._prev_y = y_norm           # Calibra el punto de partida sin mover nada
            return 0
        self.active = True
        if self._prev_y is None:
            self._prev_y = y_norm
            return 0

        dy = y_norm - self._prev_y          # + = dedos hacia abajo
        self._prev_y = y_norm
        if abs(dy) < SCROLL_DEAD_ZONE:
            dy = 0.0
        self._vel += (dy - self._vel) * SCROLL_SMOOTH

        # Dedos abajo (dy > 0) -> rueda positiva (contenido sube). Como pantalla táctil.
        direction = -1.0 if SCROLL_INVERT else 1.0
        self._accum += self._vel * SCROLL_GAIN * direction
        out = int(self._accum)
        if out:
            self._accum -= out
        return out


def pdist(a, b, w, h):
    """Distancia en píxeles entre dos landmarks (corrige la relación de aspecto)."""
    return math.hypot((a.x - b.x) * w, (a.y - b.y) * h)


def is_fist_pose(lm, w, h, size):
    """Puño cerrado: índice, medio, anular y meñique con la punta cerca de la muñeca."""
    for tip in (8, 12, 16, 20):
        if pdist(lm[0], lm[tip], w, h) / size > FIST_RATIO:
            return False
    return True


def finger_extended(lm, tip, pip, w, h):
    """Dedo estirado: la punta está bastante más lejos de la muñeca que su articulación media."""
    return pdist(lm[0], lm[tip], w, h) > pdist(lm[0], lm[pip], w, h) * FINGER_EXT_RATIO


def is_horns_pose(lm, w, h):
    """Cuernitos: índice y meñique estirados, medio y anular doblados."""
    return (finger_extended(lm, 8, 6, w, h) and finger_extended(lm, 20, 18, w, h)
            and not finger_extended(lm, 12, 10, w, h)
            and not finger_extended(lm, 16, 14, w, h))


class AltTabGesture:
    """Dispara una sola vez por pose; hay que soltarla para volver a disparar."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.count = 0
        self.fired = False

    def update(self, pose_ok):
        if not pose_ok:
            self.reset()
            return False
        self.count += 1
        if self.count >= ALTTAB_FRAMES_ON and not self.fired:
            self.fired = True
            return True
        return False


def map_to_screen(nx, ny):
    """Convierte coordenadas normalizadas de cámara a píxeles de pantalla (imagen en espejo)."""
    u = (1.0 - nx - MARGIN_X) / (1.0 - 2 * MARGIN_X)
    v = (ny - MARGIN_TOP) / (1.0 - MARGIN_TOP - MARGIN_BOTTOM)
    u = min(max(u, 0.0), 1.0)
    v = min(max(v, 0.0), 1.0)
    return u * (SCREEN_W - 1), v * (SCREEN_H - 1)


def ensure_model():
    """Descarga el modelo de manos la primera vez."""
    if os.path.exists(MODEL_PATH):
        return
    print("Descargando modelo de manos (solo la primera vez)...")
    tmp = MODEL_PATH + ".part"
    urllib.request.urlretrieve(MODEL_URL, tmp)
    os.replace(tmp, MODEL_PATH)


def draw_preview(frame, lm):
    h, w = frame.shape[:2]
    pts = [(int(p.x * w), int(p.y * h)) for p in lm]
    for a, b in HAND_CONNECTIONS:
        cv2.line(frame, pts[a], pts[b], (0, 255, 0), 1)
    for p in pts:
        cv2.circle(frame, p, 2, (0, 0, 255), -1)


# ============================================================================
# PROGRAMA PRINCIPAL
# ============================================================================
def main():
    try:
        ensure_model()
    except Exception as e:
        print(f"No se pudo descargar el modelo: {e}")
        print(f"Descárgalo manualmente de:\n{MODEL_URL}\ny guárdalo como:\n{MODEL_PATH}")
        return 1

    cap = cv2.VideoCapture(CAM_INDEX, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("No se pudo abrir la cámara.")
        return 1
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, CAM_FPS)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or CAM_WIDTH
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or CAM_HEIGHT

    options = vision.HandLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=vision.RunningMode.VIDEO,   # Modo vídeo: detecta y luego "sigue"
        num_hands=1,
        min_hand_detection_confidence=0.6,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    landmarker = vision.HandLandmarker.create_from_options(options)
    last_ts = 0                          # Los timestamps deben ser estrictamente crecientes

    mouse = Mouse()
    smoother = CursorSmoother()
    left_pinch, right_pinch = PinchDetector(), PinchDetector()
    scroll = ScrollGesture()
    alttab = AltTabGesture()
    hk_pause, hk_exit = Hotkey(VK_F8), Hotkey(VK_F9)

    paused = False
    hand_was_visible = False
    last_seen = time.monotonic()
    last_right_click = 0.0
    last_alttab = 0.0
    frame_idx = 0
    BIG = 99.0

    print(f"Ghost Mouse activo ({w}x{h}). F8 = pausa, F9 = salir.")

    try:
        while True:
            if _tracking_stop_requested or hk_exit.pressed():
                break
            if hk_pause.pressed():
                paused = not paused
                mouse.left_up()
                left_pinch.reset()
                right_pinch.reset()
                scroll.reset()
                alttab.reset()
                print("PAUSADO" if paused else "REANUDADO")

            if not cap.grab():
                time.sleep(0.01)
                continue
            if paused:
                time.sleep(0.1)
                continue

            now = time.monotonic()
            idle = (now - last_seen) > IDLE_AFTER_SEC
            skip = IDLE_EVERY_N if idle else PROCESS_EVERY_N
            frame_idx += 1
            if frame_idx % skip:
                continue

            ok, frame = cap.retrieve()
            if not ok:
                continue

            # --- Detección de mano -----------------------------------------
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            ts = int(time.monotonic() * 1000)
            if ts <= last_ts:
                ts = last_ts + 1
            last_ts = ts
            result = landmarker.detect_for_video(mp_image, ts)

            if result.hand_landmarks:
                lm = result.hand_landmarks[0]
                last_seen = now
                size = pdist(lm[0], lm[9], w, h)

                if size > 1e-6:
                    d_idx = pdist(lm[4], lm[8], w, h) / size     # pulgar-índice
                    d_mid = pdist(lm[4], lm[12], w, h) / size    # pulgar-medio

                    # --- El puño cerrado reserva la mano solo para scroll ---
                    fist_closed = is_fist_pose(lm, w, h, size)
                    palm_y = lm[9].y * h / size      # Nudillo medio: estable al cerrar el puño
                    amount = scroll.update(fist_closed, palm_y)
                    if amount:
                        mouse.wheel(amount)

                    # --- Cuernitos = Alt+Tab (también reservan la mano) ---
                    horns = (not fist_closed) and is_horns_pose(lm, w, h)
                    if alttab.update(horns) and (now - last_alttab) > ALTTAB_COOLDOWN:
                        mouse.alt_tab()
                        last_alttab = now

                    if not hand_was_visible:
                        smoother.reset()
                    hand_was_visible = True

                    if fist_closed or horns:
                        left_pinch_was = left_pinch.active
                        left_pinch.reset()
                        right_pinch.reset()
                        if left_pinch_was:
                            mouse.left_up()
                    else:
                        p = lm[POINTER_LANDMARK]
                        tx, ty = map_to_screen(p.x, p.y)
                        sx, sy = smoother.update(tx, ty)
                        mouse.move(sx, sy)

                        left_c = d_idx
                        right_c = d_mid
                        if right_pinch.active:
                            left_c = BIG
                        elif not left_pinch.active and d_idx > d_mid:
                            left_c = BIG
                        if left_pinch.active:
                            right_c = BIG
                        elif not right_pinch.active and d_mid >= d_idx:
                            right_c = BIG

                        was_left = left_pinch.active
                        is_left = left_pinch.update(left_c)
                        if is_left and not was_left:
                            mouse.left_down()
                        elif was_left and not is_left:
                            mouse.left_up()

                        was_right = right_pinch.active
                        is_right = right_pinch.update(right_c)
                        if is_right and not was_right and (now - last_right_click) > RIGHT_CLICK_COOLDOWN:
                            mouse.right_click()
                            last_right_click = now
            else:
                if hand_was_visible:
                    hand_was_visible = False
                    mouse.left_up()
                    left_pinch.reset()
                    right_pinch.reset()
                    scroll.reset()
                    alttab.reset()

            # --- Previsualización opcional (depuración) --------------------
            if SHOW_PREVIEW:
                if result.hand_landmarks:
                    draw_preview(frame, result.hand_landmarks[0])
                if scroll.active:
                    cv2.putText(frame, "SCROLL", (5, 15), cv2.FONT_HERSHEY_SIMPLEX,
                                0.5, (0, 255, 255), 1)
                if alttab.fired:
                    cv2.putText(frame, "ALT+TAB", (5, 30), cv2.FONT_HERSHEY_SIMPLEX,
                                0.5, (255, 255, 0), 1)
                cv2.imshow("Ghost Mouse (q = salir)", cv2.flip(frame, 1))
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

    except KeyboardInterrupt:
        pass
    finally:
        mouse.left_up()
        landmarker.close()
        cap.release()
        if SHOW_PREVIEW:
            cv2.destroyAllWindows()
        print("Ghost Mouse cerrado.")
    return 0


def tracking_activo():
    return _tracking_thread is not None and _tracking_thread.is_alive()


def detener_tracking():
    global _tracking_stop_requested
    if tracking_activo():
        _tracking_stop_requested = True


def iniciar_tracking():
    global _tracking_thread, _tracking_stop_requested
    if not tracking_activo():
        _tracking_stop_requested = False
        _tracking_thread = Thread(target=main, daemon=True)
        _tracking_thread.start()


if __name__ == "__main__":
    sys.exit(main())
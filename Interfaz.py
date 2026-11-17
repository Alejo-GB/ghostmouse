import queue
import threading
import time
from collections import deque

import customtkinter as ctk
from PIL import Image, ImageTk
from pathlib import Path
from tkinter import messagebox

from Codigo import detener_tracking, iniciar_tracking, tracking_activo


# Interfaz Grafica 

class GhostMouseGUI:
    def __init__(self, root):
        self.root = root
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root.title("Instrucciones")
        self.root.configure(fg_color="#0B0E13")
        self.root.protocol("WM_DELETE_WINDOW", self.cerrar_aplicacion)
        self.root.after(0, self.root.state, "zoomed")
        with Image.open(
            Path(__file__).resolve().parent / "assets" / "logo.png"
        ) as logo:
            self.icon_image = ImageTk.PhotoImage(logo.copy(), master=self.root)
        self.root.iconphoto(True, self.icon_image)

        self.tracking_active = self.stopping = False
        self.practice_window = None
        self._instruction_load_generation = 0
        self.gif_directory = Path(__file__).resolve().parent / "assets" / "gif"
        self.instruction_preference = Path.home() / ".ghostmouse" / "skip_instructions"
        if self.instruction_preference.exists():
            self.root.title("Ghost Mouse")
            self.crear_interfaz()
            self.actualizar_estado_tracking()
            self.root.after(250, self.comprobar_estado_tracking)
        else:
            self.crear_pantalla_instrucciones()

    def crear_pantalla_instrucciones(self, desde_menu=False):
        self._instruction_load_generation += 1
        generation = self._instruction_load_generation
        gifs_pendientes = []
        self.instruction_frame = ctk.CTkFrame(
            self.root, fg_color="#0B0E13", corner_radius=0
        )
        self.instruction_frame.pack(fill="both", expand=True, padx=16, pady=16)
        self.instruction_frame.grid_columnconfigure(0, weight=1)
        self.instruction_frame.grid_rowconfigure(1, weight=1)

        self.crear_etiqueta(
            self.instruction_frame, "Instrucciones", 28, "#F4F6FA", weight="bold"
        ).grid(row=0, column=0, pady=(24, 18))

        tarjetas = ctk.CTkFrame(self.instruction_frame, fg_color="transparent")
        tarjetas.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        pasos = (
            ("01", "Mueve el dedo índice", "para controlar el puntero del mouse", "puntero.gif", "PUNTERO"),
            ("02", "Junta pulgar e índice", "para hacer clic izquierdo", "clic_izquierdo.gif", "CLIC IZQUIERDO"),
            ("03", "Junta pulgar y medio", "para hacer clic derecho", "clic_derecho.gif", "CLIC DERECHO"),
            ("04", "Cierra la mano y muévela", "arriba o abajo para hacer scroll", "desplazamiento.gif", "DESPLAZAMIENTO"),
            ("05", "Forma unos cueritos", "con el índice y meñique estirados, medio y anular doblados y mantenla por un breve momento", "cuernitos.gif", "ALT+TAB"),
        )
        for columna in range(len(pasos)):
            tarjetas.grid_columnconfigure(columna, weight=1, uniform="instrucciones")
        tarjetas.grid_rowconfigure(0, weight=1)

        for columna, (numero, titulo, descripcion, gif_nombre, accion) in enumerate(pasos):
            tarjeta = ctk.CTkFrame(
                tarjetas,
                fg_color="#131923",
                corner_radius=18,
                border_width=1,
                border_color="#202A38",
            )
            tarjeta.grid(
                row=0,
                column=columna,
                sticky="nsew",
                padx=(0 if columna == 0 else 7, 0 if columna == len(pasos) - 1 else 7),
            )
            tarjeta.grid_columnconfigure(0, weight=1)
            tarjeta.grid_rowconfigure(3, weight=1)

            self.crear_etiqueta(
                tarjeta, numero, 11, "#71A7FF", weight="bold", fg_color="#18243A",
                corner_radius=10, width=34, height=28,
            ).grid(row=0, column=0, pady=(18, 10))
            self.crear_etiqueta(
                tarjeta, titulo, 15, "#F4F6FA", weight="bold",
                wraplength=220, justify="center",
            ).grid(row=1, column=0, padx=12, pady=(0, 5))
            self.crear_etiqueta(
                tarjeta, descripcion, 12, "#A6B0BE",
                wraplength=220, justify="center",
            ).grid(row=2, column=0, sticky="new", padx=12, pady=(0, 14))

            gif_label = ctk.CTkLabel(tarjeta, text="", height=360)
            gif_label.grid(row=3, column=0, sticky="nsew", padx=12, pady=(4, 2))
            gifs_pendientes.append((gif_label, self.gif_directory / gif_nombre))

            self.crear_etiqueta(
                tarjeta, accion, 10, "#A6B0BE", weight="bold"
            ).grid(row=4, column=0, padx=12, pady=(0, 18))

        acciones = ctk.CTkFrame(self.instruction_frame, fg_color="transparent")
        acciones.grid(row=2, column=0, pady=(0, 8))
        self.cargar_gifs_en_segundo_plano(gifs_pendientes, generation)

        if desde_menu:
            ctk.CTkButton(
                acciones,
                text="Regresar",
                width=230,
                height=44,
                corner_radius=12,
                font=ctk.CTkFont(family="Arial", size=14, weight="bold"),
                fg_color="#3478F6",
                hover_color="#2865D6",
                text_color="#FFFFFF",
                command=self.regresar_al_menu,
            ).pack()
            return

        ctk.CTkButton(
            acciones,
            text="Continuar",
            width=230,
            height=44,
            corner_radius=12,
            font=ctk.CTkFont(family="Arial", size=14, weight="bold"),
            fg_color="#3478F6",
            hover_color="#2865D6",
            text_color="#FFFFFF",
            command=self.mostrar_menu,
        ).pack(pady=(0, 8))
        ctk.CTkButton(
            acciones,
            text="No volver a mostrar",
            width=230,
            height=38,
            corner_radius=12,
            font=ctk.CTkFont(family="Arial", size=12),
            fg_color="#18243A",
            hover_color="#202F49",
            text_color="#C7D8FF",
            border_width=1,
            border_color="#2B3D5A",
            command=self.omitir_instrucciones,
        ).pack()

    @staticmethod
    def iterar_fotogramas_gif(ruta):
        if not ruta.is_file():
            raise FileNotFoundError(f"No se encontró el GIF de instrucciones: {ruta}")

        with Image.open(ruta) as gif:
            indice = 0
            while True:
                try:
                    gif.seek(indice)
                except EOFError:
                    if indice == 0:
                        raise ValueError(f"El GIF no contiene fotogramas: {ruta}")
                    return

                fotograma = gif.convert("RGBA")
                fotograma.thumbnail((300, 360), Image.Resampling.BILINEAR)
                yield fotograma.copy(), max(
                    20, int(gif.info.get("duration", 100))
                )
                indice += 1

    def cargar_gifs_en_segundo_plano(self, gifs_pendientes, generation):
        resultados = queue.Queue(maxsize=25)

        def cargar(indice, ruta):
            try:
                while generation == self._instruction_load_generation:
                    for fotograma, duracion in self.iterar_fotogramas_gif(ruta):
                        while generation == self._instruction_load_generation:
                            try:
                                resultados.put(
                                    (indice, fotograma, duracion, None),
                                    timeout=0.1,
                                )
                                break
                            except queue.Full:
                                continue
                        else:
                            fotograma.close()
                            return
            except (OSError, ValueError) as error:
                while generation == self._instruction_load_generation:
                    try:
                        resultados.put((indice, None, 0, error), timeout=0.1)
                        break
                    except queue.Full:
                        continue
                return

        for indice, (_, ruta) in enumerate(gifs_pendientes):
            threading.Thread(
                target=cargar, args=(indice, ruta), daemon=True
            ).start()
        fotogramas_pendientes = [deque() for _ in gifs_pendientes]
        siguientes_fotogramas = [0.0] * len(gifs_pendientes)
        imagenes_actuales = [None] * len(gifs_pendientes)

        def mostrar_resultados():
            if (
                generation != self._instruction_load_generation
                or not self.instruction_frame.winfo_exists()
            ):
                return

            while True:
                try:
                    indice, fotograma, duracion, error = resultados.get_nowait()
                except queue.Empty:
                    break

                if error is not None:
                    _, ruta = gifs_pendientes[indice]
                    messagebox.showerror(
                        "No se pudo cargar el GIF",
                        f"No fue posible abrir {ruta}:\n{error}",
                        parent=self.root,
                    )
                else:
                    fotogramas_pendientes[indice].append((fotograma, duracion))

            ahora = time.monotonic()
            for indice, (etiqueta, _) in enumerate(gifs_pendientes):
                if (
                    fotogramas_pendientes[indice]
                    and ahora >= siguientes_fotogramas[indice]
                ):
                    fotograma, duracion = fotogramas_pendientes[indice].popleft()
                    imagen = ImageTk.PhotoImage(fotograma, master=self.root)
                    fotograma.close()
                    etiqueta.configure(image=imagen, text="")
                    imagenes_actuales[indice] = imagen
                    siguientes_fotogramas[indice] = ahora + duracion / 1000

            if generation == self._instruction_load_generation:
                self.root.after(10, mostrar_resultados)

        self.root.after(10, mostrar_resultados)

    def omitir_instrucciones(self):
        try:
            self.instruction_preference.parent.mkdir(parents=True, exist_ok=True)
            self.instruction_preference.write_text("1", encoding="utf-8")
        except OSError as error:
            messagebox.showerror(
                "No se pudo guardar la preferencia",
                f"No fue posible guardar que quieres omitir las instrucciones:\n{error}",
                parent=self.root,
            )
            return
        self.mostrar_menu()

    def mostrar_menu(self):
        self._instruction_load_generation += 1
        self.instruction_frame.destroy()
        self.root.title("Ghost Mouse")
        self.crear_interfaz()
        self.actualizar_estado_tracking()
        self.root.after(250, self.comprobar_estado_tracking)

    def mostrar_instrucciones(self):
        self.menu_frame.pack_forget()
        self.root.title("Instrucciones")
        self.crear_pantalla_instrucciones(desde_menu=True)

    def regresar_al_menu(self):
        self._instruction_load_generation += 1
        self.instruction_frame.destroy()
        self.root.title("Ghost Mouse")
        self.menu_frame.pack(fill="both", expand=True, padx=16, pady=14)

    def crear_interfaz(self):
        self.menu_frame = ctk.CTkFrame(self.root, fg_color="#0B0E13", corner_radius=0)
        self.menu_frame.pack(fill="both", expand=True, padx=16, pady=14)

        # Altura aumentada de 500 a 620 para evitar que los elementos inferiores se corten
        contenido = ctk.CTkFrame(self.menu_frame, width=440, height=620, fg_color="transparent")
        contenido.place(relx=0.5, rely=0.5, anchor="center")
        contenido.pack_propagate(False)

        encabezado = ctk.CTkFrame(contenido, fg_color="transparent")
        encabezado.pack(fill="x", pady=(0, 6))

        logo = ctk.CTkFrame(encabezado, width=36, height=36, fg_color="#18243A", corner_radius=12)
        logo.pack(side="left")
        logo.pack_propagate(False)
        ctk.CTkLabel(logo, text="GM", font=ctk.CTkFont(family="Arial", size=15, weight="bold"), text_color="#71A7FF").place(relx=0.5, rely=0.5, anchor="center")

        identidad = ctk.CTkFrame(encabezado, fg_color="transparent")
        identidad.pack(side="left", padx=14)
        ctk.CTkLabel(identidad, text="Ghost Mouse", font=ctk.CTkFont(family="Arial", size=18, weight="bold"), text_color="#F4F6FA").pack(anchor="w")
        ctk.CTkLabel(identidad, text="MOUSE DIGITAL", font=ctk.CTkFont(family="Arial", size=10, weight="bold"), text_color="#7C8798").pack(anchor="w", pady=(3, 0))

        tarjeta = ctk.CTkFrame(contenido, fg_color="#131923", corner_radius=22, border_width=1, border_color="#202A38")
        tarjeta.pack(fill="x")

        estado = ctk.CTkFrame(tarjeta, fg_color="transparent")
        estado.pack(fill="x", padx=12, pady=(8, 2))
        self.status_dot = ctk.CTkLabel(estado, text="●", font=ctk.CTkFont(family="Arial", size=17), text_color="#596579", height=20)
        self.status_dot.pack(side="left", padx=(0, 9))
        self.status_label = ctk.CTkLabel(estado, text="Listo para iniciar", font=ctk.CTkFont(family="Arial", size=13, weight="bold"), text_color="#C7CFDA", height=20)
        self.status_label.pack(side="left")

        ctk.CTkLabel(tarjeta, text="Mueve el dedo índice para controlar el puntero. Junta el dedo indice+pulgar para hacer clic izquierdo. Junta el dedo medio+pulgar para hacer clic derecho. Cierra el puño y mueve la mano arriba o abajo para desplazarte. Forma unos cueritos y manten brevemmente para despalzarte por ventana..", font=ctk.CTkFont(family="Arial", size=11), text_color="#8793A5", wraplength=270, justify="left", height=42).pack(fill="x", padx=12, pady=(0, 6))

        self.action_button = ctk.CTkButton(tarjeta, text="Iniciar", width=280, height=36, corner_radius=14, font=ctk.CTkFont(family="Arial", size=14, weight="bold"), fg_color="#3478F6", hover_color="#2865D6", text_color="#FFFFFF", command=self.alternar_tracking)
        self.action_button.pack(anchor="center", pady=(0, 8))

        controles = ctk.CTkFrame(contenido, fg_color="#111720", corner_radius=20, border_width=1, border_color="#202A38")
        controles.pack(fill="x", pady=(5, 0))
        ctk.CTkLabel(controles, text="CONTROLES", font=ctk.CTkFont(family="Arial", size=9, weight="bold"), text_color="#7C8798", height=20).pack(anchor="w", padx=12, pady=(7, 3))

        self.agregar_control(controles, "Mueve el dedo índice", "Mover el puntero", "#B80F0F")
        self.agregar_control(controles, "Índice + pulgar", "Clic izquierdo", "#71A7FF")
        self.agregar_control(controles, "Medio + pulgar", "Clic derecho", "#B19AFF")
        self.agregar_control(controles, "Puño cerrado + movimiento", "Desplazamiento", "#45D483")
        self.agregar_control(controles, "Cuernitos", "Alt+Tab", "#F9A74B")

        ctk.CTkButton(
            contenido,
            text="Instrucciones",
            width=280,
            height=36,
            corner_radius=12,
            font=ctk.CTkFont(family="Arial", size=13, weight="bold"),
            fg_color="#18243A",
            hover_color="#202F49",
            text_color="#C7D8FF",
            border_width=1,
            border_color="#2B3D5A",
            command=self.mostrar_instrucciones,
        ).pack(fill="x", pady=(5, 0))

        ctk.CTkButton(contenido, text="Cerrar aplicación", width=280, height=30, corner_radius=10, fg_color="transparent", hover_color="#1A222E", text_color="#8793A5", font=ctk.CTkFont(family="Arial", size=11), command=self.cerrar_aplicacion).pack(anchor="center", pady=(2, 0))

    @staticmethod
    def crear_etiqueta(parent, texto, tamano, color, weight="normal", **opciones):
        return ctk.CTkLabel(
            parent,
            text=texto,
            font=ctk.CTkFont(family="Arial", size=tamano, weight=weight),
            text_color=color,
            **opciones,
        )

    def agregar_control(self, parent, tecla, accion, color):
        fila = ctk.CTkFrame(parent, fg_color="transparent")
        fila.pack(fill="x", padx=12, pady=(0, 4))
        self.crear_etiqueta(fila, tecla, 11, color, weight="bold", height=20).pack(side="left")
        self.crear_etiqueta(fila, accion, 11, "#A6B0BE", height=20).pack(side="right")

    def actualizar_estado_tracking(self):
        if self.tracking_active:
            self.status_dot.configure(text_color="#45D483")
            if self.stopping:
                self.status_label.configure(text="Deteniendo seguimiento...")
                self.action_button.configure(text="Deteniendo...", state="disabled")
            else:
                self.status_label.configure(text="Seguimiento activo")
                self.action_button.configure(text="Detener/F9", state="normal", fg_color="#D94B55", hover_color="#B93843")
        else:
            self.status_dot.configure(text_color="#596579")
            self.status_label.configure(text="Listo para iniciar")
            self.action_button.configure(text="Iniciar seguimiento", state="normal", fg_color="#3478F6", hover_color="#2865D6")

    def alternar_tracking(self):
        if tracking_activo():
            detener_tracking()
            self.stopping = True
            self.actualizar_estado_tracking()
            return
        iniciar_tracking()
        self.tracking_active, self.stopping = tracking_activo(), False
        self.actualizar_estado_tracking()
        self.mostrar_ventana_practica()
        self.root.iconify()
        if self.practice_window is not None and self.practice_window.winfo_exists():
            self.practice_window.lift()

    def mostrar_ventana_practica(self):
        if self.practice_window is not None and self.practice_window.winfo_exists():
            self.practice_window.lift()
            return


        #Ventana de practica
        self.practice_window = ctk.CTkToplevel(self.root)
        self.practice_window.title("Práctica de Ghost Mouse")
        self.practice_window.geometry("390x390")
        self.practice_window.resizable(False, False)
        self.practice_window.configure(fg_color="#0B0E13")
        self.practice_window.iconphoto(True, self.icon_image)
        self.practice_window.protocol("WM_DELETE_WINDOW", self.cerrar_ventana_practica)

        tarjeta = ctk.CTkFrame(self.practice_window, fg_color="#131923", corner_radius=22, border_width=1, border_color="#202A38")
        tarjeta.pack(fill="both", expand=True, padx=16, pady=16)

        self.crear_etiqueta(tarjeta, "Instrucciones", 25, "#F4F6FA", weight="bold").pack(pady=(25, 14))
        self.crear_etiqueta(
            tarjeta, "Mueve el dedo índice para controlar el puntero. Junta pulgar e índice para el clic izquierdo, o pulgar y medio para el derecho. Mantén el clic izquierdo para arrastrar. Cierra el puño y mueve la mano arriba o abajo para desplazarte.",
            12, "#A6B0BE", wraplength=310, justify="center",
        ).pack(fill="x", padx=20, pady=(0, 16))
        self.crear_etiqueta(
            tarjeta, "Practica conmigo el click y el arrastre", 13, "#F4F6FA",
            weight="bold", wraplength=300, justify="center",
        ).pack(fill="x", padx=20, pady=(0, 12))

        self.practice_feedback = self.crear_etiqueta(
            tarjeta, "Prueba el clic izquierdo o derecho sobre el botón",
            10, "#8793A5", wraplength=300,
        )
        self.practice_feedback.pack(fill="x", padx=20, pady=(0, 8))
        self.practice_button = ctk.CTkButton(
            tarjeta,
            text="Practicar clic",
            width=280,
            height=42,
            corner_radius=14,
            font=ctk.CTkFont(family="Arial", size=14, weight="bold"),
            fg_color="#238B57",
            hover_color="#1C7046",
            text_color="#FFFFFF",
            command=lambda: self.registrar_clic_practica("izquierdo"),
        )
        self.practice_button.pack(anchor="center", pady=(0, 16))
        self.practice_button.bind(
            "<Button-3>",
            lambda _event: self.registrar_clic_practica("derecho"),
        )

        ctk.CTkButton(
            tarjeta,
            text="Cerrar ventana de practica",
            width=280,
            height=36,
            corner_radius=12,
            fg_color="transparent",
            hover_color="#1A222E",
            text_color="#8793A5",
            font=ctk.CTkFont(family="Arial", size=11),
            command=self.cerrar_ventana_practica,
        ).pack(side="bottom", anchor="center", pady=(0, 16))

    def registrar_clic_practica(self, tipo):
        self.practice_feedback.configure(
            text=f"¡Clic {tipo} detectado! Sigue practicando."
        )

    def cerrar_ventana_practica(self):
        if self.practice_window is not None and self.practice_window.winfo_exists():
            self.practice_window.destroy()
        self.practice_window = None

    def comprobar_estado_tracking(self):
        thread_activo = tracking_activo()
        if thread_activo != self.tracking_active:
            self.tracking_active, self.stopping = thread_activo, False
            self.actualizar_estado_tracking()
        self.root.after(250, self.comprobar_estado_tracking)

    def cerrar_aplicacion(self):
        self._instruction_load_generation += 1
        detener_tracking()
        self.root.destroy()


if __name__ == "__main__":
    root = ctk.CTk()
    app = GhostMouseGUI(root)
    root.mainloop()
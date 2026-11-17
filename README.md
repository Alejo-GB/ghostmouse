# Ghost Mouse

Aplicacion para Windows que permite controlar el cursor con gestos de la mano
capturados por una camara web. La aplicacion procesa la imagen localmente y
puede mover el cursor, hacer clic, desplazarse y cambiar de ventana con Alt+Tab.

## Ejecutar desde el codigo

Requiere Windows, Python compatible con MediaPipe 1.1.0 y una camara web.

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python Interfaz.py
```

La primera ejecucion de `Codigo.py` descarga el modelo de deteccion de manos
si no esta junto al codigo. Para compilar el ejecutable en Windows, ejecuta
`build_portable.bat` desde el repositorio; requiere que `.venv` exista.

## Descargar

Los ejecutables para usuarios deben publicarse en la seccion **Releases** de
GitHub, no junto al codigo fuente. Consulta las instrucciones incluidas con
cada version antes de usar el programa.

## Controles

- **F8**: pausar o reanudar el control.
- **F9**: salir.
- Pulgar e indice: clic izquierdo; mantener el gesto permite arrastrar.
- Pulgar y dedo medio: clic derecho.
- Puño cerrado: desplazamiento.
- Gesto de cuernitos: Alt+Tab.

El programa necesita acceso a la camara y puede generar acciones de raton y
teclado en Windows mientras esta activo. Usa F8 para pausarlo y F9 para salir.

## Publicacion

Antes de publicar, agrega una licencia de proyecto y verifica que tienes
permiso para redistribuir el modelo `hand_landmarker.task`, las imagenes, los
GIF y los iconos incluidos. Atribuye sus autores y licencias cuando corresponda.

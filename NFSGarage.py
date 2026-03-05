import sys
import os
import ctypes
import shutil
import random
import rarfile
import zipfile
try:
    import py7zr
    HAS_7Z = True
except ImportError:
    HAS_7Z = False
import subprocess
import json
from PyQt6.QtWidgets import (
    QApplication, QWidget, QPushButton, QFileDialog,
    QLabel, QVBoxLayout, QHBoxLayout, QMessageBox,
    QFrame, QListWidget, QAbstractItemView, QListWidgetItem, QDialog
)
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QPoint, QTimer, QPointF
from PyQt6.QtGui import QPainter, QColor, QLinearGradient, QBrush, QIcon, QFont

# ──────────────────────────────────────────────
#  RUTAS PORTABLES
#  - resource_path: para archivos que van DENTRO del exe (icon, dlls)
#  - user_data_path: para datos del usuario (config, historial) → AppData
# ──────────────────────────────────────────────
def resource_path(relative_path):
    """Ruta a recursos empaquetados con PyInstaller, o junto al .py en dev."""
    try:
        base = sys._MEIPASS
    except AttributeError:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative_path)

def user_data_path(filename):
    """Ruta persistente en AppData/Roaming/NFSGarage — funciona compilado o en dev."""
    folder = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "NFSGarage")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, filename)


class Star:
    def __init__(self, width, height, layer=None):
        self.x = random.uniform(0, width)
        self.y = random.uniform(0, height)
        # 3 capas: lejanas (pequeñas/lentas), medias, cercanas (grandes/rápidas)
        if layer is None:
            layer = random.choices([0, 1, 2], weights=[50, 35, 15])[0]
        self.layer = layer
        if layer == 0:   # lejanas
            self.size  = random.uniform(0.3, 0.8)
            self.speed = random.uniform(0.04, 0.10)
            self.alpha = random.randint(50, 120)
        elif layer == 1: # medias
            self.size  = random.uniform(0.8, 1.4)
            self.speed = random.uniform(0.10, 0.22)
            self.alpha = random.randint(120, 180)
        else:            # cercanas
            self.size  = random.uniform(1.4, 2.2)
            self.speed = random.uniform(0.22, 0.45)
            self.alpha = random.randint(180, 255)

    def move(self, width, height):
        self.y += self.speed
        if self.y > height:
            self.y = 0
            self.x = random.uniform(0, width)


class ModPreviewDialog(QDialog):
    """Ventana de vista previa antes de instalar el mod."""
    def __init__(self, parent, car_name, bin_labels, lang):
        super().__init__(parent)
        self.setWindowTitle("MOD PREVIEW" if lang == "EN" else "VISTA PREVIA")
        self.setFixedSize(460, 300)
        self.setStyleSheet("QWidget { background-color: #050A14; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(35, 30, 35, 30)
        layout.setSpacing(16)

        # Título
        title = QLabel("MOD PREVIEW" if lang == "EN" else "VISTA PREVIA DEL MOD")
        title.setStyleSheet("color: #4A90E2; font-size: 13px; font-weight: bold; letter-spacing: 2px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Separador
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: rgba(74,144,226,0.3); border: none;")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        # Carpeta del auto
        lbl_car_title = QLabel("FOLDER TO INSTALL:" if lang == "EN" else "CARPETA A INSTALAR:")
        lbl_car_title.setStyleSheet("color: rgba(74,144,226,0.5); font-size: 9px; font-weight: bold; letter-spacing: 1px;")
        layout.addWidget(lbl_car_title)

        lbl_car = QLabel(car_name.upper() if car_name != "Not detected" else "— NOT DETECTED —")
        car_color = "#FFFFFF" if car_name != "Not detected" else "rgba(255,255,255,0.3)"
        lbl_car.setStyleSheet(f"color: {car_color}; font-size: 14px; font-weight: bold;")
        layout.addWidget(lbl_car)

        # BINs
        lbl_bin_title = QLabel("MANUFACTURER BIN:" if lang == "EN" else "BIN DE FABRICANTE:")
        lbl_bin_title.setStyleSheet("color: rgba(74,144,226,0.5); font-size: 9px; font-weight: bold; letter-spacing: 1px;")
        layout.addWidget(lbl_bin_title)

        lbl_bin = QLabel(bin_labels if bin_labels != "None" else "— NONE —")
        bin_color = "#FFFFFF" if bin_labels != "None" else "rgba(255,255,255,0.3)"
        lbl_bin.setStyleSheet(f"color: {bin_color}; font-size: 11px;")
        lbl_bin.setWordWrap(True)
        layout.addWidget(lbl_bin)

        layout.addStretch()

        # Botones
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        btn_cancel = QPushButton("CANCEL" if lang == "EN" else "CANCELAR")
        btn_cancel.setFixedHeight(40)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet("""
            QPushButton { background: transparent; color: rgba(255,255,255,0.4);
                border: 1px solid rgba(255,255,255,0.15); border-radius: 4px; font-weight: bold; font-size: 11px; }
            QPushButton:hover { color: white; border-color: rgba(255,255,255,0.4); }
        """)
        btn_cancel.clicked.connect(self.reject)

        btn_install = QPushButton("INSTALL" if lang == "EN" else "INSTALAR")
        btn_install.setFixedHeight(40)
        btn_install.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_install.setStyleSheet("""
            QPushButton { background: rgba(74,144,226,0.1); color: #4A90E2;
                border: 1px solid rgba(74,144,226,0.4); border-radius: 4px; font-weight: bold; font-size: 11px; }
            QPushButton:hover { background: #4A90E2; color: white; border-color: #4A90E2; }
        """)
        btn_install.clicked.connect(self._confirm)

        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_install)
        layout.addLayout(btn_layout)

    def _confirm(self):
        self.accept()


class ModLoaderGUI(QWidget):
    def __init__(self):
        if not self.is_admin():
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
            sys.exit()

        super().__init__()

        # ── Ícono portable ──────────────────────────────────────────────
        icon_path = resource_path("icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.lang = "EN"
        self.texts = {
            "EN": {
                "title": "NFS Garage",
                "install_ml": "INSTALL MODLOADER",
                "active_ml": "MODLOADER ACTIVE",
                "import": "IMPORT FROM FOLDER",
                "import_rar": "IMPORT FROM RAR",
                "library": "LIBRARY",
                "mods_folder": "MODS FOLDER",
                "launch": "LAUNCH GAME",
                "history_title": "MOD HISTORY",
                "clear_hist": "CLEAR HISTORY",
                "lib_models": "INSTALLED MODELS",
                "lib_bins": "DETECTED BINS",
                "select_game": "Please select the NFS Most Wanted root folder.",
                "error_exe": "Invalid folder. speed.exe is required.",
                "success_ml": "ModLoader installed correctly.",
                "mod_installed": "Mod installed",
                "no_content": "No valid content detected.",
                "confirm_del": "Permanently delete"
            },
            "ES": {
                "title": "NFS Garage",
                "install_ml": "INSTALAR MODMANAGER",
                "active_ml": "MODMANAGER ACTIVO",
                "import": "IMPORTAR CARPETA",
                "import_rar": "IMPORTAR RAR",
                "library": "BIBLIOTECA",
                "mods_folder": "CARPETA DE MODS",
                "launch": "INICIAR JUEGO",
                "history_title": "HISTORIAL DE MODS",
                "clear_hist": "LIMPIAR HISTORIAL",
                "lib_models": "MODELOS INSTALADOS",
                "lib_bins": "BINS DETECTADOS",
                "select_game": "Por favor, seleccione la carpeta raíz de NFS Most Wanted.",
                "error_exe": "Carpeta inválida. Se requiere speed.exe.",
                "success_ml": "ModLoader instalado correctamente.",
                "mod_installed": "Mod instalado",
                "no_content": "No se detectó contenido válido.",
                "confirm_del": "¿Eliminar permanentemente"
            }
        }

        self.setWindowTitle("NFS Garage")
        self.setFixedSize(700, 800)
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowMinimizeButtonHint |
            Qt.WindowType.MSWindowsFixedSizeDialogHint
        )

        # ── Rutas de datos del usuario (portables) ─────────────────────
        self.config_file  = user_data_path("config.txt")
        self.history_file = user_data_path("history.json")

        self.game_path = ""
        self.stars = [Star(700, 800) for _ in range(200)]
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_background)
        self.timer.start(30)

        self.load_configuration()
        self.init_ui()
        self.load_persistent_history()
        self.check_modloader_status()

    # ── Helpers ─────────────────────────────────────────────────────────

    def is_admin(self):
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False

    def load_configuration(self):
        if os.path.exists(self.config_file):
            with open(self.config_file, "r", encoding="utf-8") as f:
                self.game_path = f.read().strip()

        if not self.game_path or not os.path.exists(os.path.join(self.game_path, "speed.exe")):
            self.select_initial_game_path()
        else:
            self.update_internal_paths(self.game_path)

    def select_initial_game_path(self):
        QTimer.singleShot(100, self._show_path_dialog)

    def _show_path_dialog(self):
        QMessageBox.information(self, "NFS Garage", self.texts[self.lang]["select_game"])
        path = QFileDialog.getExistingDirectory(self, "Select Game Folder")
        if path and os.path.exists(os.path.join(path, "speed.exe")):
            path = os.path.normpath(path)
            with open(self.config_file, "w", encoding="utf-8") as f:
                f.write(path)
            self.game_path = path
            self.update_internal_paths(path)
        else:
            QMessageBox.critical(self, "Error", self.texts[self.lang]["error_exe"])
            sys.exit()

    def update_internal_paths(self, path):
        self.game_path   = path
        self.addons_path  = os.path.join(self.game_path, "ADDONS")
        self.disabled_path = os.path.join(self.addons_path, "DISABLED")
        self.game_exe    = os.path.join(self.game_path, "speed.exe")
        os.makedirs(os.path.join(self.disabled_path, "CARS"), exist_ok=True)
        os.makedirs(os.path.join(self.disabled_path, "BINS"), exist_ok=True)

    # ── Fondo animado ────────────────────────────────────────────────────

    def update_background(self):
        for star in self.stars:
            star.move(self.width(), self.height())
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QColor(5, 10, 20))
        gradient.setColorAt(1, QColor(2, 4, 8))
        painter.fillRect(self.rect(), QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        for star in self.stars:
            painter.setBrush(QColor(255, 255, 255, star.alpha))
            painter.drawEllipse(QPointF(star.x, star.y), star.size, star.size)

    # ── UI ───────────────────────────────────────────────────────────────

    def init_ui(self):
        self.layout_principal = QVBoxLayout(self)
        self.layout_principal.setContentsMargins(0, 0, 0, 0)

        header = QHBoxLayout()
        header.setContentsMargins(25, 25, 25, 0)

        self.btn_menu = QPushButton("≡")
        self.btn_menu.setFixedSize(35, 30)
        self.btn_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_menu.setStyleSheet("QPushButton { color: white; font-size: 24px; background: transparent; border: none; } QPushButton:hover { color: #4A90E2; }")
        self.btn_menu.clicked.connect(self.toggle_side_menu)

        self.btn_lang = QPushButton("EN")
        self.btn_lang.setFixedSize(45, 30)
        self.btn_lang.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_lang.setStyleSheet("""
            QPushButton {
                color: white; font-weight: bold;
                background: rgba(74,144,226,0.05);
                border: 1px solid rgba(74,144,226,0.2);
                border-radius: 4px;
            }
            QPushButton:hover { background: #4A90E2; border: 1px solid #4A90E2; }
        """)
        self.btn_lang.clicked.connect(self.toggle_language)

        header.addWidget(self.btn_menu)
        header.addStretch()
        header.addWidget(self.btn_lang)
        self.layout_principal.addLayout(header)
        self.layout_principal.addStretch(1)

        estilo_btn = """
            QPushButton {
                background-color: rgba(255,255,255,0.02);
                color: #4A90E2;
                border: 1px solid rgba(74,144,226,0.15);
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
                min-width: 280px;
                min-height: 48px;
            }
            QPushButton:hover { background-color: rgba(74,144,226,0.08); border: 1px solid #4A90E2; color: white; }
            QPushButton:disabled { color: #2ECC71; border: 1px solid rgba(46,204,113,0.2); }
        """

        contenedor_botones = QVBoxLayout()
        contenedor_botones.setAlignment(Qt.AlignmentFlag.AlignCenter)
        contenedor_botones.setSpacing(18)

        self.btn_install_base = QPushButton()
        self.btn_import       = QPushButton()
        self.btn_import_rar   = QPushButton()
        self.btn_library      = QPushButton()
        self.btn_mods_folder  = QPushButton()
        self.btn_launch       = QPushButton()

        for btn in [self.btn_install_base, self.btn_import, self.btn_import_rar,
                    self.btn_library, self.btn_mods_folder, self.btn_launch]:
            btn.setStyleSheet(estilo_btn)
            contenedor_botones.addWidget(btn)

        self.btn_install_base.clicked.connect(self.install_modloader_surgical)
        self.btn_import.clicked.connect(self.select_file)
        self.btn_import_rar.clicked.connect(self.select_rar)
        self.btn_library.clicked.connect(self.open_library)
        self.btn_mods_folder.clicked.connect(self.open_mods_folder)
        self.btn_launch.clicked.connect(self.launch_game)

        self.layout_principal.addLayout(contenedor_botones)
        self.layout_principal.addStretch(1)

        # ── Panel historial (slide-in) ───────────────────────────────────
        self.panel_history = QFrame(self)
        self.panel_history.setGeometry(-280, 0, 280, 800)
        self.panel_history.setStyleSheet("QFrame { background-color: #050A14; border-right: 1px solid rgba(74,144,226,0.3); }")

        layout_h = QVBoxLayout(self.panel_history)
        layout_h.setContentsMargins(20, 40, 20, 25)

        header_h = QHBoxLayout()
        self.lbl_h_title = QLabel()
        self.lbl_h_title.setStyleSheet("color: white; font-weight: bold; font-size: 14px; border: none;")

        self.btn_close = QPushButton("←")
        self.btn_close.setFixedSize(30, 30)
        self.btn_close.setStyleSheet("QPushButton { color: #4A90E2; font-size: 22px; background: transparent; border: none; } QPushButton:hover { color: white; }")
        self.btn_close.clicked.connect(self.toggle_side_menu)

        header_h.addWidget(self.lbl_h_title)
        header_h.addStretch()
        header_h.addWidget(self.btn_close)
        layout_h.addLayout(header_h)

        self.list_history = QListWidget()
        self.list_history.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list_history.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.list_history.setStyleSheet("""
            QListWidget { background: transparent; border: none; color: white; outline: none; }
            QListWidget::item { border: none; background: transparent; }
            QListWidget::item:selected { background: transparent; }
            QScrollBar:vertical {
                width: 4px; background: transparent; margin: 4px 0px; border: none;
            }
            QScrollBar::handle:vertical {
                background: rgba(74, 144, 226, 0.35); border-radius: 2px; min-height: 20px;
            }
            QScrollBar::handle:vertical:hover { background: rgba(74, 144, 226, 0.7); }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px; background: none; border: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
        """)
        layout_h.addWidget(self.list_history)

        self.btn_clear = QPushButton()
        self.btn_clear.setFixedSize(180, 35)
        self.btn_clear.setStyleSheet("QPushButton { background-color: rgba(231,76,60,0.05); color: #E74C3C; border: 1px solid rgba(231,76,60,0.3); border-radius: 4px; font-weight: bold; }")
        self.btn_clear.clicked.connect(self.clear_history)

        layout_btn_h = QHBoxLayout()
        layout_btn_h.addStretch()
        layout_btn_h.addWidget(self.btn_clear)
        layout_btn_h.addStretch()
        layout_h.addLayout(layout_btn_h)

        self.menu_animation = QPropertyAnimation(self.panel_history, b"pos")
        self.menu_animation.setDuration(350)
        self.menu_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.update_ui_texts()

    # ── Idioma ───────────────────────────────────────────────────────────

    def toggle_language(self):
        self.lang = "ES" if self.lang == "EN" else "EN"
        self.btn_lang.setText(self.lang)
        self.update_ui_texts()

    def update_ui_texts(self):
        t = self.texts[self.lang]
        self.btn_install_base.setText(t["install_ml"] if self.btn_install_base.isEnabled() else t["active_ml"])
        self.btn_import.setText(t["import"])
        self.btn_import_rar.setText(t["import_rar"])
        self.btn_library.setText(t["library"])
        self.btn_mods_folder.setText(t["mods_folder"])
        self.btn_launch.setText(t["launch"])
        self.lbl_h_title.setText(t["history_title"])
        self.btn_clear.setText(t["clear_hist"])

    # ── ModLoader ────────────────────────────────────────────────────────

    def check_modloader_status(self):
        has_dll = os.path.exists(os.path.join(self.game_path, "d3d9.dll"))
        has_ini = os.path.exists(os.path.join(self.game_path, "modloader.ini"))
        if has_dll and has_ini:
            self.btn_install_base.setText(self.texts[self.lang]["active_ml"])
            self.btn_install_base.setEnabled(False)

    def install_modloader_surgical(self):
        try:
            shutil.copy2(resource_path("d3d9.dll"),      os.path.join(self.game_path, "d3d9.dll"))
            shutil.copy2(resource_path("modloader.ini"), os.path.join(self.game_path, "modloader.ini"))
            # ── Carpetas con nombre unificado (guión bajo, sin espacio) ──
            os.makedirs(os.path.join(self.addons_path, "CARS_REPLACE"),             exist_ok=True)
            os.makedirs(os.path.join(self.addons_path, "FRONTEND", "MANUFACTURERS"), exist_ok=True)
            self.check_modloader_status()
            QMessageBox.information(self, "Success", self.texts[self.lang]["success_ml"])
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ── Menú lateral ─────────────────────────────────────────────────────

    def toggle_side_menu(self):
        is_open = self.panel_history.x() >= 0
        destination = QPoint(-280, 0) if is_open else QPoint(0, 0)
        self.menu_animation.setEndValue(destination)
        self.menu_animation.start()

    # ── Juego ────────────────────────────────────────────────────────────

    def launch_game(self):
        if os.path.exists(self.game_exe):
            subprocess.Popen([self.game_exe], cwd=self.game_path, shell=False)
        else:
            QMessageBox.warning(self, "Error", "speed.exe not found")

    def open_mods_folder(self):
        if os.path.exists(self.addons_path):
            os.startfile(self.addons_path)

    # ── Importar mods ────────────────────────────────────────────────────

    def select_rar(self):
        """Selecciona un archivo comprimido y lo instala automáticamente."""
        title = "Select MOD Archive" if self.lang == "EN" else "Seleccione el archivo del MOD"
        path, _ = QFileDialog.getOpenFileName(
            self, title, "",
            "Compressed files (*.rar *.zip *.7z)"
        )
        if path:
            temp_dir = os.path.join(os.environ["TEMP"], "nfs_work_dir")
            try:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                os.makedirs(temp_dir)
                self.extract_archive(path, temp_dir)
                self.import_logic(temp_dir, "folder")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))
            finally:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)

    def select_file(self):
        title = "Select MOD Folder" if self.lang == "EN" else "Seleccione la carpeta del MOD"
        path = QFileDialog.getExistingDirectory(self, title)
        if path:
            self.import_logic(path, "folder")

    def extract_archive(self, archive_path, dest_dir):
        """Extrae cualquier formato soportado al directorio destino."""
        ext = os.path.splitext(archive_path)[1].lower()
        if ext == ".rar":
            with rarfile.RarFile(archive_path) as rf:
                rf.extractall(dest_dir)
        elif ext == ".zip":
            with zipfile.ZipFile(archive_path, 'r') as zf:
                zf.extractall(dest_dir)
        elif ext == ".7z":
            if HAS_7Z:
                with py7zr.SevenZipFile(archive_path, mode='r') as zf:
                    zf.extractall(dest_dir)
            else:
                raise Exception("7z support requires py7zr: pip install py7zr")
        else:
            raise Exception(f"Unsupported format: {ext}")

    def import_logic(self, source_path, import_type):
        temp_dir = os.path.join(os.environ["TEMP"], "nfs_work_dir")
        try:
            if import_type == "rar":
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                os.makedirs(temp_dir)
                self.extract_archive(source_path, temp_dir)
                work_path = temp_dir
            else:
                work_path = source_path

            car_folder_src, car_name, bins_to_move = None, "Not detected", []

            # ── Señales de carpeta de auto ───────────────────────────────
            # Busca por nombre base SIN extensión (insensible a mayúsculas)
            # Cubre: GEOMETRY.BIN, geometry.bin, GEOMETRY, Geometry, etc.
            CAR_SIGNALS_BASE = {"geometry", "car", "fe", "attributes", "vinyls",
                                "colors", "damage", "textures", "secondarylogo"}

            # BINs de marcas: nombre empieza con número (ej: 101-NISSAN, 27-FORD_HD)
            def is_manufacturer_bin(filename):
                base = os.path.splitext(filename)[0]
                return base[0].isdigit() if base else False

            def get_car_signals(files):
                """Retorna cuántas señales de auto hay en la lista de archivos."""
                bases = {os.path.splitext(f)[0].lower() for f in files}
                return len(CAR_SIGNALS_BASE & bases)

            for root, dirs, files in os.walk(work_path):
                in_frontend = any(p in root.upper() for p in ["FRONTEND", "MANUFACTURERS"])

                # Detectar carpeta de auto: tiene GEOMETRY o al menos 2 señales
                bases = {os.path.splitext(f)[0].lower() for f in files}
                has_geometry = "geometry" in bases
                signal_count = len(CAR_SIGNALS_BASE & bases)

                if (has_geometry or signal_count >= 2) and not in_frontend:
                    car_folder_src = root
                    car_name = os.path.basename(root)

                # Detectar BINs de marcas: nombre empieza con número
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext == ".bin" and is_manufacturer_bin(f):
                        bins_to_move.append(os.path.join(root, f))

            # Si seleccionó directamente la carpeta raíz del auto
            if car_folder_src is None and not bins_to_move:
                files = [f for f in os.listdir(work_path)
                         if os.path.isfile(os.path.join(work_path, f))]
                bases = {os.path.splitext(f)[0].lower() for f in files}
                if "geometry" in bases or len(CAR_SIGNALS_BASE & bases) >= 2:
                    car_folder_src = work_path
                    car_name = os.path.basename(work_path)

            if car_folder_src or bins_to_move:
                bin_labels = ", ".join(os.path.basename(x) for x in bins_to_move) if bins_to_move else "None"

                # ── Vista previa antes de instalar ───────────────────────
                preview = ModPreviewDialog(self, car_name, bin_labels, self.lang)
                if not preview.exec():
                    return  # Usuario canceló

                if car_folder_src:
                    dest_car = os.path.join(self.addons_path, "CARS_REPLACE", car_name)
                    if os.path.exists(dest_car):
                        shutil.rmtree(dest_car)
                    shutil.copytree(car_folder_src, dest_car)

                if bins_to_move:
                    dest_man = os.path.join(self.addons_path, "FRONTEND", "MANUFACTURERS")
                    os.makedirs(dest_man, exist_ok=True)
                    for b in bins_to_move:
                        shutil.copy2(b, os.path.join(dest_man, os.path.basename(b)))

                self.add_to_history(car_name, bin_labels)
                self.save_history_to_disk(car_name, bin_labels)
                QMessageBox.information(self, "Done", f"{self.texts[self.lang]['mod_installed']} {car_name}.\nBINs: {bin_labels}")
            else:
                QMessageBox.warning(self, "Error", self.texts[self.lang]["no_content"])

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
        finally:
            if import_type == "rar" and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    # ── Historial ────────────────────────────────────────────────────────

    def add_to_history(self, car_name, bin_names):
        item = QListWidgetItem(self.list_history)
        widget = QWidget()
        lay = QHBoxLayout(widget)
        lay.setContentsMargins(5, 5, 5, 5)
        txt = QLabel(f"MOD: {car_name.upper()}\nBIN: {bin_names}")
        txt.setStyleSheet("color: white; font-size: 10px; background: transparent; border: none;")
        btn = QPushButton("🗑")
        btn.setFixedSize(25, 25)
        btn.setStyleSheet("QPushButton { background: transparent; color: #555; border: none; font-size: 14px; } QPushButton:hover { color: #E74C3C; }")
        btn.clicked.connect(lambda: self.delete_history_item(item))
        lay.addWidget(txt)
        lay.addStretch()
        lay.addWidget(btn)
        item.setSizeHint(widget.sizeHint())
        self.list_history.addItem(item)
        self.list_history.setItemWidget(item, widget)

    def save_history_to_disk(self, car, bins):
        data = []
        if os.path.exists(self.history_file):
            with open(self.history_file, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                except:
                    data = []
        if not any(d["car"] == car for d in data):
            data.append({"car": car, "bins": bins})
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    def load_persistent_history(self):
        if os.path.exists(self.history_file):
            with open(self.history_file, "r", encoding="utf-8") as f:
                try:
                    for entry in json.load(f):
                        self.add_to_history(entry["car"], entry["bins"])
                except:
                    pass

    def delete_history_item(self, item):
        row = self.list_history.row(item)
        self.list_history.takeItem(row)
        if os.path.exists(self.history_file):
            with open(self.history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if row < len(data):
                data.pop(row)
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    def clear_history(self):
        self.list_history.clear()
        if os.path.exists(self.history_file):
            os.remove(self.history_file)

    # ── Biblioteca ───────────────────────────────────────────────────────

    def open_library(self):
        if not hasattr(self, "ventana_bib") or self.ventana_bib is None:
            self.ventana_bib = QWidget(self)
            self.ventana_bib.setWindowTitle("Library")
            self.ventana_bib.setFixedSize(500, 650)
            self.ventana_bib.setWindowFlags(
                Qt.WindowType.Window |
                Qt.WindowType.WindowCloseButtonHint |
                Qt.WindowType.MSWindowsFixedSizeDialogHint
            )
            self.ventana_bib.setStyleSheet("QWidget { background-color: #050A14; }")
            layout_bib = QVBoxLayout(self.ventana_bib)
            layout_bib.setContentsMargins(30, 30, 30, 30)
            layout_bib.setSpacing(10)

            title_lib = QLabel("GARAGE REPOSITORY")
            title_lib.setStyleSheet("color: #4A90E2; font-size: 16px; font-weight: bold; letter-spacing: 2px; margin-bottom: 20px;")
            title_lib.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout_bib.addWidget(title_lib)

            self.lbl_lib_models = QLabel()
            self.lbl_lib_models.setStyleSheet("color: rgba(74,144,226,0.5); font-weight: bold; font-size: 10px; margin-left: 5px;")
            layout_bib.addWidget(self.lbl_lib_models)

            self.list_cars = QListWidget()
            self.list_cars.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.list_cars.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
            self._apply_list_style(self.list_cars)
            layout_bib.addWidget(self.list_cars)

            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setFixedHeight(3)
            sep.setStyleSheet("background-color: rgba(74,144,226,0.4); border: none; margin: 10px 0px;")
            layout_bib.addWidget(sep)

            self.lbl_lib_bins = QLabel()
            self.lbl_lib_bins.setStyleSheet("color: rgba(74,144,226,0.5); font-weight: bold; font-size: 10px; margin-left: 5px;")
            layout_bib.addWidget(self.lbl_lib_bins)

            self.list_bins = QListWidget()
            self.list_bins.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.list_bins.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
            self._apply_list_style(self.list_bins)
            layout_bib.addWidget(self.list_bins)

        self.lbl_lib_models.setText(self.texts[self.lang]["lib_models"])
        self.lbl_lib_bins.setText(self.texts[self.lang]["lib_bins"])
        self.load_library_data()
        self.ventana_bib.show()

    def _apply_list_style(self, lw):
        lw.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
                color: white;
                outline: none;
            }
            QListWidget::item {
                background: transparent;
                border: none;
                border-radius: 4px;
                padding: 2px 4px;
            }
            QListWidget::item:hover { background: transparent; }
            QScrollBar:vertical {
                width: 4px;
                background: transparent;
                margin: 4px 0px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background: rgba(74, 144, 226, 0.35);
                border-radius: 2px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(74, 144, 226, 0.7);
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
                background: none;
                border: none;
            }
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: none;
            }
        """)

    def load_library_data(self):
        self.list_cars.clear()
        self.list_bins.clear()

        for folder, active in [
            (os.path.join(self.addons_path,   "CARS_REPLACE"), True),
            (os.path.join(self.disabled_path, "CARS"),         False),
        ]:
            if os.path.exists(folder):
                for d in sorted(os.listdir(folder)):
                    if os.path.isdir(os.path.join(folder, d)):
                        self.create_library_item(self.list_cars, d, "car", active)

        for folder, active in [
            (os.path.join(self.addons_path,   "FRONTEND", "MANUFACTURERS"), True),
            (os.path.join(self.disabled_path, "BINS"),                      False),
        ]:
            if os.path.exists(folder):
                for f in sorted(os.listdir(folder)):
                    if f.lower().endswith(".bin"):
                        self.create_library_item(self.list_bins, f, "bin", active)

    def create_library_item(self, list_widget, name, item_type, active):
        item = QListWidgetItem(list_widget)
        widget = QWidget()
        lay = QHBoxLayout(widget)
        lay.setContentsMargins(5, 5, 5, 5)

        color = "#4A90E2" if active else "rgba(255,255,255,0.3)"
        txt = QLabel(name.upper())
        txt.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 500; border: none; background: transparent;")

        btn_toggle = QPushButton("ON" if active else "OFF")
        btn_toggle.setFixedSize(35, 20)
        btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_toggle.setStyleSheet(f"""
            QPushButton {{ background-color: transparent; color: {color}; border: 1px solid {color}; border-radius: 2px; font-size: 9px; }}
            QPushButton:hover {{ background-color: {color}; color: black; }}
        """)
        btn_toggle.clicked.connect(lambda: self.toggle_mod(name, item_type, active))

        btn_del = QPushButton("🗑")
        btn_del.setFixedSize(25, 20)
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.setStyleSheet("QPushButton { background: transparent; color: rgba(255,255,255,0.2); border: none; font-size: 14px; } QPushButton:hover { color: #E74C3C; }")
        btn_del.clicked.connect(lambda: self.delete_permanently(name, item_type, active))

        lay.addWidget(txt)
        lay.addStretch()
        lay.addWidget(btn_toggle)
        lay.addWidget(btn_del)
        item.setSizeHint(widget.sizeHint())
        list_widget.addItem(item)
        list_widget.setItemWidget(item, widget)

    def toggle_mod(self, name, item_type, active):
        try:
            if item_type == "car":
                src = os.path.join(self.addons_path,   "CARS_REPLACE", name) if active else os.path.join(self.disabled_path, "CARS", name)
                dst = os.path.join(self.disabled_path, "CARS",         name) if active else os.path.join(self.addons_path,   "CARS_REPLACE", name)
            else:
                src = os.path.join(self.addons_path,   "FRONTEND", "MANUFACTURERS", name) if active else os.path.join(self.disabled_path, "BINS", name)
                dst = os.path.join(self.disabled_path, "BINS",                      name) if active else os.path.join(self.addons_path,   "FRONTEND", "MANUFACTURERS", name)
            if os.path.exists(src):
                shutil.move(src, dst)
                self.load_library_data()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def delete_permanently(self, name, item_type, active):
        reply = QMessageBox.question(
            self, "Confirm",
            f"{self.texts[self.lang]['confirm_del']} {name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if item_type == "car":
                    path = os.path.join(self.addons_path,   "CARS_REPLACE", name) if active else os.path.join(self.disabled_path, "CARS", name)
                    if os.path.isdir(path): shutil.rmtree(path)
                else:
                    path = os.path.join(self.addons_path,   "FRONTEND", "MANUFACTURERS", name) if active else os.path.join(self.disabled_path, "BINS", name)
                    if os.path.exists(path): os.remove(path)
                self.load_library_data()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))


# ── Entry point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        gui = ModLoaderGUI()
        gui.show()
        sys.exit(app.exec())
    except Exception as e:
        ctypes.windll.user32.MessageBoxW(0, f"Error Crítico: {str(e)}", "NFS Garage Crash", 0x10)


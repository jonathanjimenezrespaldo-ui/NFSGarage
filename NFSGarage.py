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
    QFrame, QListWidget, QAbstractItemView, QListWidgetItem, QDialog, QLineEdit
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


# ── Temas de color ──────────────────────────────────────────────────────────
THEMES = {
    "blue": {
        "accent":       "#4A90E2",
        "accent_rgba":  "74,144,226",
        "bg_top":       "5, 10, 20",
        "bg_bot":       "2, 4, 8",
        "panel_bg":     "#050A14",
        "star_color":   "255,255,255",
    },
    "purple": {
        "accent":       "#9B59B6",
        "accent_rgba":  "155,89,182",
        "bg_top":       "8, 3, 18",
        "bg_bot":       "3, 1, 8",
        "panel_bg":     "#080312",
        "star_color":   "200,170,255",
    },
    "black": {
        "accent":       "#C0C0C0",
        "accent_rgba":  "192,192,192",
        "bg_top":       "3, 3, 3",
        "bg_bot":       "0, 0, 0",
        "panel_bg":     "#080808",
        "star_color":   "255,255,255",
    },
}

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


class LanguageSelectDialog(QDialog):
    """Pantalla inicial de selección de idioma."""
    def __init__(self):
        super().__init__()
        self.selected_lang = "EN"
        self.setWindowTitle("NFS Garage")
        self.setFixedSize(400, 260)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.MSWindowsFixedSizeDialogHint)
        self.setStyleSheet("QWidget { background-color: #080808; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(50, 40, 50, 40)
        layout.setSpacing(20)

        title = QLabel("NFS GARAGE")
        title.setStyleSheet("color: white; font-size: 22px; font-weight: bold; letter-spacing: 4px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        sub = QLabel("Select your language / Seleccione su idioma")
        sub.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 10px;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub)

        layout.addStretch()

        btn_style = """
            QPushButton {
                background: rgba(255,255,255,0.04); color: rgba(255,255,255,0.7);
                border: 1px solid rgba(255,255,255,0.15); border-radius: 4px;
                font-size: 13px; font-weight: bold; min-height: 42px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.1); color: white; border-color: rgba(255,255,255,0.4); }
        """
        btn_en = QPushButton("English")
        btn_en.setStyleSheet(btn_style)
        btn_en.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_en.clicked.connect(lambda: self._pick("EN"))

        btn_es = QPushButton("Español")
        btn_es.setStyleSheet(btn_style)
        btn_es.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_es.clicked.connect(lambda: self._pick("ES"))

        layout.addWidget(btn_en)
        layout.addWidget(btn_es)

    def _pick(self, lang):
        self.selected_lang = lang
        self.accept()


class FolderHintDialog(QDialog):
    """Mensaje estético cuando IMPORT FROM FOLDER no detecta contenido válido."""
    def __init__(self, parent, lang, theme="blue"):
        super().__init__(parent)
        t = THEMES[theme]; a = t["accent"]; ar = t["accent_rgba"]; pb = t["panel_bg"]
        self.setWindowTitle("NFS Garage")
        self.setFixedSize(420, 210)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.MSWindowsFixedSizeDialogHint)
        self.setStyleSheet(f"QDialog {{ background-color: {pb}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(35, 30, 35, 30)
        layout.setSpacing(14)

        icon_lbl = QLabel("⚠")
        icon_lbl.setStyleSheet("color: #E67E22; font-size: 28px; background: transparent;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_lbl)

        if lang == "EN":
            msg = "No valid content detected.<br><br>Make sure the selected folder contains a <b>ModLoader-compatible mod</b>.<br>It should include files like CARS_REPLACE or similar."
        else:
            msg = "No se detectó contenido válido.<br><br>Asegúrese de que la carpeta seleccionada contenga un <b>mod compatible con ModLoader</b>.<br>Debe incluir archivos como CARS_REPLACE o similares."

        lbl = QLabel(msg)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setStyleSheet("color: rgba(255,255,255,0.85); font-size: 11px; background: transparent;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        layout.addStretch()

        btn = QPushButton("OK")
        btn.setFixedHeight(38)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{ background: rgba({ar},0.1); color: {a};
                border: 1px solid rgba({ar},0.4); border-radius: 4px;
                font-weight: bold; font-size: 11px; }}
            QPushButton:hover {{ background: {a}; color: white; }}
        """)
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)


class ExtractHintDialog(QDialog):
    """Mensaje estético cuando IMPORT FROM RAR falla — sugiere extraer manualmente."""
    def __init__(self, parent, lang, theme="blue"):
        super().__init__(parent)
        t = THEMES[theme]; a = t["accent"]; ar = t["accent_rgba"]; pb = t["panel_bg"]
        self.setWindowTitle("NFS Garage")
        self.setFixedSize(420, 230)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.MSWindowsFixedSizeDialogHint)
        self.setStyleSheet(f"QDialog {{ background-color: {pb}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(35, 30, 35, 30)
        layout.setSpacing(14)

        icon_lbl = QLabel("⚠")
        icon_lbl.setStyleSheet("color: #E67E22; font-size: 28px; background: transparent;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_lbl)

        if lang == "EN":
            msg = "Could not process this archive automatically.<br><br>In the <b>IMPORT FROM RAR</b> section, locate your file,<br>extract it with right-click → Extract here,<br>then use <b>IMPORT FROM FOLDER</b> to select the extracted folder."
        else:
            msg = "No se pudo procesar este archivo automáticamente.<br><br>En la sección <b>IMPORTAR RAR</b>, ubique su archivo,<br>extráigalo con click derecho → Extraer aquí,<br>luego use <b>IMPORTAR CARPETA</b> para seleccionar la carpeta extraída."

        lbl = QLabel(msg)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setStyleSheet("color: rgba(255,255,255,0.85); font-size: 11px; background: transparent;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        layout.addStretch()

        btn = QPushButton("OK")
        btn.setFixedHeight(38)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{ background: rgba({ar},0.1); color: {a};
                border: 1px solid rgba({ar},0.4); border-radius: 4px;
                font-weight: bold; font-size: 11px; }}
            QPushButton:hover {{ background: {a}; color: white; }}
        """)
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)


class ModPreviewDialog(QDialog):
    """Ventana de vista previa antes de instalar el mod."""
    def __init__(self, parent, car_name, bin_labels, lang, will_replace=False, theme="blue"):
        super().__init__(parent)
        t = THEMES[theme]; a = t["accent"]; ar = t["accent_rgba"]; pb = t["panel_bg"]
        self.setWindowTitle("mod preview" if lang == "EN" else "vista previa")
        self.setFixedSize(460, 300)
        self.setStyleSheet(f"QWidget {{ background-color: {pb}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(35, 30, 35, 30)
        layout.setSpacing(16)

        # Título
        title = QLabel("MOD PREVIEW" if lang == "EN" else "VISTA PREVIA DEL MOD")
        title.setStyleSheet(f"color: {a}; font-size: 13px; font-weight: bold; letter-spacing: 2px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Separador
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background: rgba({ar},0.3); border: none;")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        # Carpeta del auto
        lbl_car_title = QLabel("FOLDER TO INSTALL:" if lang == "EN" else "CARPETA A INSTALAR:")
        lbl_car_title.setStyleSheet(f"color: rgba({ar},0.5); font-size: 9px; font-weight: bold; letter-spacing: 1px;")
        layout.addWidget(lbl_car_title)

        lbl_car = QLabel(car_name.upper() if car_name != "Not detected" else "— NOT DETECTED —")
        car_color = "#FFFFFF" if car_name != "Not detected" else "rgba(255,255,255,0.3)"
        lbl_car.setStyleSheet(f"color: {car_color}; font-size: 14px; font-weight: bold;")
        layout.addWidget(lbl_car)

        # BINs
        lbl_bin_title = QLabel("MANUFACTURER BIN:" if lang == "EN" else "BIN DE FABRICANTE:")
        lbl_bin_title.setStyleSheet(f"color: rgba({ar},0.5); font-size: 9px; font-weight: bold; letter-spacing: 1px;")
        layout.addWidget(lbl_bin_title)

        lbl_bin = QLabel(bin_labels if bin_labels != "None" else "— NONE —")
        bin_color = "#FFFFFF" if bin_labels != "None" else "rgba(255,255,255,0.3)"
        lbl_bin.setStyleSheet(f"color: {bin_color}; font-size: 11px;")
        lbl_bin.setWordWrap(True)
        layout.addWidget(lbl_bin)

        # Aviso de sustitución — debajo del BIN
        if will_replace:
            lbl_warn = QLabel("⚠  " + ("This mod will replace an existing installation" if lang == "EN" else "Este mod reemplazará una instalación existente"))
            lbl_warn.setStyleSheet("color: #E67E22; font-size: 9px; font-weight: bold; margin-top: 2px;")
            lbl_warn.setWordWrap(True)
            layout.addWidget(lbl_warn)

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
            QPushButton {{ background: rgba({ar},0.1); color: {a};
                border: 1px solid rgba({ar},0.4); border-radius: 4px; font-weight: bold; font-size: 11px; }}
            QPushButton:hover {{ background: {a}; color: white; border-color: {a}; }}
        """)
        btn_install.clicked.connect(self._confirm)

        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_install)
        layout.addLayout(btn_layout)

    def _confirm(self):
        self.accept()


class ModLoaderGUI(QWidget):
    def __init__(self, initial_lang="EN"):
        if not self.is_admin():
            args = " ".join(sys.argv) + f" --lang={initial_lang}"
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, args, None, 1)
            sys.exit()

        super().__init__()

        # ── Ícono portable ──────────────────────────────────────────────
        icon_path = resource_path("icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.lang = initial_lang if initial_lang else "ES"
        self.theme = "blue"  # tema por defecto
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
                "no_content": "No valid content detected.\nTry extracting manually and use IMPORT FROM FOLDER.",
                "confirm_del": "Permanently delete",
                "mod_replaced": "This mod will replace an existing installation",
                "how_to_use": "How to use?",
                "welcome": "WELCOME",
                "how_to_use_steps": "1. INSTALL MODLOADER\nInstalls the files needed for the game to load mods. Only done once.\n\n2. IMPORT MOD (FOLDER / RAR)\nSelect the mod folder or archive. The app detects content and installs automatically.\n\n3. MOD PREVIEW\nBefore installing you will see a preview with the folder name and detected BINs. Confirm or cancel.\n\n4. LIBRARY\nView all installed mods. Enable or disable them with ON/OFF without deleting, or remove permanently.\n\n5. MOD HISTORY\nThe left panel keeps a record of all imported mods with their name and BINs. Delete entries individually or clear all.\n\n6. MODS FOLDER\nOpens the game ADDONS folder directly so you can inspect files manually.\n\n7. LAUNCH GAME\nLaunches NFS Most Wanted directly from the app."
            },
            "ES": {
                "title": "NFS Garage",
                "install_ml": "INSTALAR MODLOADER",
                "active_ml": "MODLOADER ACTIVO",
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
                "no_content": "No se detectó contenido válido.\nIntente extraer manualmente y use IMPORTAR CARPETA.",
                "confirm_del": "¿Eliminar permanentemente",
                "mod_replaced": "Este mod reemplazará una instalación existente",
                "how_to_use": "¿Cómo usar?",
                "welcome": "BIENVENIDO",
                "how_to_use_steps": "1. INSTALAR MODLOADER\nInstala los archivos necesarios para que el juego cargue mods. Solo se hace una vez.\n\n2. IMPORTAR MOD (CARPETA / RAR)\nSeleccione la carpeta o archivo comprimido. La app detecta el contenido e instala automáticamente.\n\n3. VISTA PREVIA\nAntes de instalar verá una pantalla con el nombre de la carpeta y los BINs detectados. Confirme o cancele.\n\n4. BIBLIOTECA\nVea todos sus mods instalados. Actívelos o desactívelos con ON/OFF sin borrarlos, o elimínelos permanentemente.\n\n5. HISTORIAL DE MODS\nEl panel lateral guarda un registro de todos los mods importados con su nombre y BINs. Borre entradas o limpie todo.\n\n6. CARPETA DE MODS\nAbre la carpeta ADDONS del juego directamente para inspeccionar archivos manualmente.\n\n7. INICIAR JUEGO\nLanza NFS Most Wanted directamente desde la app."
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
        self.config_file   = user_data_path("config.txt")
        self.history_file  = user_data_path("history.json")
        self.settings_file = user_data_path("settings.json")

        self.game_path = ""
        self.stars = [Star(700, 800) for _ in range(200)]
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_background)
        self.timer.start(30)

        self.load_configuration()
        self.load_settings()
        self.init_ui()
        self.load_persistent_history()
        self.check_modloader_status()

    # ── Helpers ─────────────────────────────────────────────────────────

    def is_admin(self):
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False

    def load_settings(self):
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.lang  = data.get("lang",  "ES")
                    self.theme = data.get("theme", "blue")
            except:
                pass

    def save_settings(self):
        with open(self.settings_file, "w", encoding="utf-8") as f:
            json.dump({"lang": self.lang, "theme": self.theme}, f)

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
        self.themed_msg("NFS Garage", self.texts[self.lang]["select_game"], "info")
        path = QFileDialog.getExistingDirectory(self, "Select Game Folder")
        if path and os.path.exists(os.path.join(path, "speed.exe")):
            path = os.path.normpath(path)
            with open(self.config_file, "w", encoding="utf-8") as f:
                f.write(path)
            self.game_path = path
            self.update_internal_paths(path)
        else:
            self.themed_msg("Error", self.texts[self.lang]["error_exe"], "error")
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
        # Actualizar library si está abierta
        if hasattr(self, "ventana_bib") and self.ventana_bib and self.ventana_bib.isVisible():
            t = THEMES[self.theme]
            pb = t["panel_bg"]
            ar = t["accent_rgba"]
            self.ventana_bib.setStyleSheet(f"QWidget {{ background-color: {pb}; }}")
            search_style = f"QLineEdit {{ background: rgba(255,255,255,0.04); border: 1px solid rgba({ar},0.2); border-radius: 4px; color: rgba(255,255,255,0.7); font-size: 10px; padding: 4px 8px; }} QLineEdit:focus {{ border: 1px solid rgba({ar},0.6); color: white; }}"
            if hasattr(self, "search_cars"): self.search_cars.setStyleSheet(search_style)
            if hasattr(self, "search_bins"): self.search_bins.setStyleSheet(search_style)
            if hasattr(self, "lbl_lib_models"): self.lbl_lib_models.setStyleSheet(f"color: rgba({ar},0.5); font-weight: bold; font-size: 10px; margin-left: 5px;")
            if hasattr(self, "lbl_lib_bins"): self.lbl_lib_bins.setStyleSheet(f"color: rgba({ar},0.5); font-weight: bold; font-size: 10px; margin-left: 5px;")

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = THEMES[self.theme]
        bg_top = [int(x) for x in t["bg_top"].split(",")]
        bg_bot = [int(x) for x in t["bg_bot"].split(",")]
        sc = [int(x) for x in t["star_color"].split(",")]
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QColor(*bg_top))
        gradient.setColorAt(1, QColor(*bg_bot))
        painter.fillRect(self.rect(), QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        for star in self.stars:
            painter.setBrush(QColor(sc[0], sc[1], sc[2], star.alpha))
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
        self.btn_menu.setStyleSheet("QPushButton { color: white; font-size: 24px; background: transparent; border: none; } QPushButton:hover { color: #4A90E2; }")  # THEME_BTN_MENU
        self.btn_menu.clicked.connect(self.toggle_side_menu)

        self.btn_settings = QPushButton("⚙")
        self.btn_settings.setFixedSize(35, 30)
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.setStyleSheet("QPushButton { color: white; font-size: 18px; background: transparent; border: none; } QPushButton:hover { color: #4A90E2; }")  # THEME_BTN_SETTINGS
        self.btn_settings.clicked.connect(self.open_settings)

        header.addWidget(self.btn_menu)
        header.addStretch()
        header.addWidget(self.btn_settings)
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


        self.btn_close.setStyleSheet("QPushButton { color: rgba(255,255,255,0.4); font-size: 22px; background: transparent; border: none; } QPushButton:hover { color: white; }")
        self.btn_close.clicked.connect(self.toggle_side_menu)

        header_h.addWidget(self.lbl_h_title)
        header_h.addStretch()
        header_h.addWidget(self.btn_close)
        layout_h.addLayout(header_h)

        self.search_history = QLineEdit()
        self.search_history.setFixedHeight(28)
        self.search_history.setStyleSheet("")
        self.search_history.textChanged.connect(self._filter_history)
        layout_h.addWidget(self.search_history)

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
            /* THEME_SCROLL_HISTORY */
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

        # ── Botón How to Use — esquina inferior derecha — siempre visible ──
        self.btn_how = QPushButton(self)
        self.btn_how.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_how.setStyleSheet("""
            QPushButton {
                color: rgba(255,255,255,0.4);
                background: transparent;
                border: none;
                font-size: 11px;
                text-decoration: underline;
                font-family: Georgia, serif;
            }
            QPushButton:hover { color: white; }
        """)
        self.btn_how.move(self.width() - 130, self.height() - 35)
        self.btn_how.resize(120, 25)
        self.btn_how.setText(self.texts[self.lang]["how_to_use"])
        self.btn_how.clicked.connect(self.show_how_to_use)
        self.btn_how.show()
        self.btn_how.raise_()
        self.apply_theme()

        # ── Welcome panel con esquina redondeada ─────────────────────────
        self.welcome_panel = QFrame(self)
        self.welcome_panel.setFixedSize(220, 55)
        px = (self.width() - 220) // 2
        py = (self.height() - 55) // 2
        self.welcome_panel.move(px, py)
        self.welcome_panel.setStyleSheet("""
            QFrame {
                background-color: rgba(5, 8, 18, 0.92);
                border-radius: 14px;
                border: 1px solid rgba(74,144,226,0.15);
            }
        """)
        lbl_w = QLabel(self.welcome_panel)
        lbl_w.setGeometry(0, 0, 220, 55)
        lbl_w.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_w.setStyleSheet("""
            color: white;
            font-size: 15px;
            font-family: Georgia, serif;
            letter-spacing: 4px;
            background: transparent;
            border: none;
        """)
        lbl_w.setText(self.texts[self.lang]["welcome"])
        self.welcome_panel.raise_()
        self._welcome_opacity = 255
        QTimer.singleShot(1000, self._start_welcome_fade)

    def _start_welcome_fade(self):
        self._fade_timer = QTimer()
        self._fade_timer.timeout.connect(self._fade_welcome)
        self._fade_timer.start(30)

    def _fade_welcome(self):
        self._welcome_opacity -= 4
        if self._welcome_opacity <= 0:
            self._fade_timer.stop()
            self.welcome_panel.hide()
        else:
            alpha_panel = int(self._welcome_opacity * 0.92 / 255 * 100) / 100
            self.welcome_panel.setStyleSheet(f"""
                QFrame {{
                    background-color: rgba(5, 8, 18, {alpha_panel});
                    border-radius: 14px;
                    border: 1px solid rgba(74,144,226,{alpha_panel * 0.15:.2f});
                }}
            """)
            lbl = self.welcome_panel.findChild(QLabel)
            if lbl:
                lbl.setStyleSheet(f"""
                    color: rgba(255,255,255,{self._welcome_opacity});
                    font-size: 15px;
                    font-family: Georgia, serif;
                    letter-spacing: 4px;
                    background: transparent;
                    border: none;
                """)

    def show_how_to_use(self):
        t = THEMES[self.theme]
        a = t["accent"]
        ar = t["accent_rgba"]
        pb = t["panel_bg"]

        dlg = QDialog(self)
        dlg.setWindowTitle("How to use" if self.lang == "EN" else "Cómo usar")
        dlg.setFixedSize(500, 560)
        dlg.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.MSWindowsFixedSizeDialogHint)
        dlg.setStyleSheet(f"QDialog {{ background-color: {pb}; }}")
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(35, 30, 35, 30)

        title = QLabel("HOW TO USE" if self.lang == "EN" else "CÓMO USAR")
        title.setStyleSheet(f"color: {a}; font-size: 14px; font-weight: bold; letter-spacing: 2px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background: rgba({ar},0.3); border: none; margin: 8px 0;")
        sep.setFixedHeight(1)
        lay.addWidget(sep)

        steps = QLabel(self.texts[self.lang]["how_to_use_steps"])
        steps.setStyleSheet("color: rgba(255,255,255,0.85); font-size: 11px; line-height: 1.6;")
        steps.setWordWrap(True)
        steps.setAlignment(Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(steps)

        lay.addStretch()
        dlg.exec()

    # ── Idioma ───────────────────────────────────────────────────────────


    def open_settings(self):
        t = THEMES[self.theme]
        a = t["accent"]
        ar = t["accent_rgba"]
        pb = t["panel_bg"]

        dlg = QDialog(self)
        dlg.setWindowTitle("Settings" if self.lang == "EN" else "Ajustes")
        dlg.setFixedSize(360, 320)
        dlg.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.MSWindowsFixedSizeDialogHint)
        dlg.setStyleSheet(f"QDialog {{ background-color: {pb}; }}")

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(35, 30, 35, 30)
        lay.setSpacing(18)

        # Título
        lbl_title = QLabel("SETTINGS" if self.lang == "EN" else "AJUSTES")
        lbl_title.setStyleSheet(f"color: {a}; font-size: 14px; font-weight: bold; letter-spacing: 2px;")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl_title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background: rgba({ar},0.3); border: none;")
        sep.setFixedHeight(1)
        lay.addWidget(sep)

        # Idioma
        lbl_lang = QLabel("LANGUAGE" if self.lang == "EN" else "IDIOMA")
        lbl_lang.setStyleSheet(f"color: rgba({ar},0.6); font-size: 9px; font-weight: bold; letter-spacing: 1px;")
        lay.addWidget(lbl_lang)

        lang_row = QHBoxLayout()
        lang_row.setSpacing(10)
        btn_style_lang = lambda active: f"""QPushButton {{
            background: {"rgba(" + ar + ",0.15)" if active else "transparent"};
            color: {a if active else "rgba(255,255,255,0.4)"};
            border: 1px solid {"rgba(" + ar + ",0.6)" if active else "rgba(255,255,255,0.1)"};
            border-radius: 4px; font-weight: bold; font-size: 11px; min-height: 32px;
        }} QPushButton:hover {{ background: rgba({ar},0.15); color: {a}; border-color: rgba({ar},0.6); }}"""

        btn_en = QPushButton("English")
        btn_es = QPushButton("Español")
        btn_en.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_es.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_en.setStyleSheet(btn_style_lang(self.lang == "EN"))
        btn_es.setStyleSheet(btn_style_lang(self.lang == "ES"))

        def set_lang(l):
            self.lang = l
            self.update_ui_texts()
            self.save_settings()
            dlg.close()
            self.open_settings()

        btn_en.clicked.connect(lambda: set_lang("EN"))
        btn_es.clicked.connect(lambda: set_lang("ES"))
        lang_row.addWidget(btn_en)
        lang_row.addWidget(btn_es)
        lay.addLayout(lang_row)

        # Tema
        lbl_theme = QLabel("THEME" if self.lang == "EN" else "TEMA")
        lbl_theme.setStyleSheet(f"color: rgba({ar},0.6); font-size: 9px; font-weight: bold; letter-spacing: 1px;")
        lay.addWidget(lbl_theme)

        theme_row = QHBoxLayout()
        theme_row.setSpacing(10)

        theme_labels = {"blue": ("Blue" if self.lang == "EN" else "Azul"), "purple": ("Purple" if self.lang == "EN" else "Morado"), "black": ("Black" if self.lang == "EN" else "Negro")}
        theme_colors = {"blue": "#4A90E2", "purple": "#9B59B6", "black": "#C0C0C0"}

        for key, label in theme_labels.items():
            tc = theme_colors[key]
            btn_t = QPushButton(label)
            btn_t.setCursor(Qt.CursorShape.PointingHandCursor)
            is_active = self.theme == key
            btn_t.setStyleSheet(f"""QPushButton {{
                background: {"rgba(" + tc.lstrip("#") + ",0.15)" if is_active else "transparent"};
                color: {tc if is_active else "rgba(255,255,255,0.4)"};
                border: 1px solid {tc if is_active else "rgba(255,255,255,0.1)"};
                border-radius: 4px; font-weight: bold; font-size: 10px; min-height: 32px;
            }} QPushButton:hover {{ color: {tc}; border-color: {tc}; }}""")

            def make_set_theme(k):
                def _set():
                    self.apply_theme(k)
                    self.save_settings()
                    dlg.close()
                    self.open_settings()
                return _set

            btn_t.clicked.connect(make_set_theme(key))
            theme_row.addWidget(btn_t)

        lay.addLayout(theme_row)
        lay.addStretch()
        dlg.exec()

    def apply_theme(self, theme_name=None):
        if theme_name:
            self.theme = theme_name
        t = THEMES[self.theme]
        a = t["accent"]
        ar = t["accent_rgba"]
        pb = t["panel_bg"]

        # Botones principales
        estilo_btn = f"""
            QPushButton {{
                background-color: rgba(255,255,255,0.02);
                color: {a};
                border: 1px solid rgba({ar},0.15);
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
                min-width: 280px;
                min-height: 48px;
            }}
            QPushButton:hover {{ background-color: rgba({ar},0.08); border: 1px solid {a}; color: white; }}
            QPushButton:disabled {{ color: #2ECC71; border: 1px solid rgba(46,204,113,0.2); }}
        """
        for btn in [self.btn_install_base, self.btn_import, self.btn_import_rar,
                    self.btn_library, self.btn_mods_folder, self.btn_launch]:
            btn.setStyleSheet(estilo_btn)

        # Panel historial
        self.panel_history.setStyleSheet(f"QFrame {{ background-color: {pb}; border-right: 1px solid rgba({ar},0.3); }}")

        # Scrollbar historial
        scroll_list_style = f"""
            QListWidget {{ background: transparent; border: none; color: white; outline: none; }}
            QListWidget::item {{ border: none; background: transparent; }}
            QListWidget::item:selected {{ background: transparent; }}
            QScrollBar:vertical {{ width: 4px; background: transparent; margin: 4px 0px; border: none; }}
            QScrollBar::handle:vertical {{ background: rgba({ar},0.35); border-radius: 2px; min-height: 20px; }}
            QScrollBar::handle:vertical:hover {{ background: rgba({ar},0.7); }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; background: none; border: none; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
        """
        if hasattr(self, "list_history"):
            self.list_history.setStyleSheet(scroll_list_style)
        if hasattr(self, "list_cars"):
            self.list_cars.setStyleSheet(scroll_list_style)
        if hasattr(self, "list_bins"):
            self.list_bins.setStyleSheet(scroll_list_style)

        # Botón menú
        self.btn_menu.setStyleSheet(f"QPushButton {{ color: white; font-size: 24px; background: transparent; border: none; }} QPushButton:hover {{ color: {a}; }}")

        # Botón settings
        self.btn_settings.setStyleSheet(f"QPushButton {{ color: white; font-size: 18px; background: transparent; border: none; }} QPushButton:hover {{ color: {a}; }}")

        # How to use
        search_style = f"QLineEdit {{ background: rgba(255,255,255,0.04); border: 1px solid rgba({ar},0.2); border-radius: 4px; color: rgba(255,255,255,0.7); font-size: 10px; padding: 4px 8px; }} QLineEdit:focus {{ border: 1px solid rgba({ar},0.6); color: white; }}"
        if hasattr(self, "search_history"):
            self.search_history.setStyleSheet(search_style)

        self.btn_close.setStyleSheet(f"QPushButton {{ color: rgba(255,255,255,0.3); font-size: 22px; background: transparent; border: none; }} QPushButton:hover {{ color: {a}; }}")

        self.btn_how.setStyleSheet(f"""
            QPushButton {{ color: rgba(255,255,255,0.4); background: transparent; border: none;
                font-size: 11px; text-decoration: underline; font-family: Georgia, serif; }}
            QPushButton:hover {{ color: white; }}
        """)

        self.update()

    def toggle_language(self):
        self.lang = "ES" if self.lang == "EN" else "EN"
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
        if hasattr(self, "btn_how"):
            self.btn_how.setText(t["how_to_use"])
        if hasattr(self, "search_history"):
            self.search_history.setPlaceholderText("Buscar carpeta" if self.lang == "ES" else "Search folder")

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
            self.themed_msg("Success" if self.lang == "EN" else "Éxito", self.texts[self.lang]["success_ml"], "info")
        except Exception as e:
            self.themed_msg("Error", str(e), "error")

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
            self.themed_msg("Error", "speed.exe not found", "warn")

    def open_mods_folder(self):
        if os.path.exists(self.addons_path):
            os.startfile(self.addons_path)

    # ── Importar mods ────────────────────────────────────────────────────

    def select_rar(self):
        """Selecciona un archivo comprimido y lo instala automáticamente."""
        title = "Select mod archive" if self.lang == "EN" else "Seleccione el archivo del mod"
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
                self.import_logic(temp_dir, "rar_extracted")
            except Exception:
                ExtractHintDialog(self, self.lang, self.theme).exec()
            # También mostrar hint si no se detectó contenido válido
            finally:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)

    def select_file(self):
        # Un solo explorador nativo — selecciona carpeta directamente
        title = "Select mod folder" if self.lang == "EN" else "Seleccione la carpeta del mod"
        path = QFileDialog.getExistingDirectory(self, title)
        if path:
            self.import_logic(path, "folder")

    def extract_single(self, archive_path, dest_dir):
        """Extrae un solo archivo comprimido a dest_dir."""
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
                # Fallback: intentar con 7-Zip si está instalado en el sistema
                seven_zip = r"C:\Program Files\7-Zip\7z.exe"
                if os.path.exists(seven_zip):
                    subprocess.run([seven_zip, "x", archive_path, f"-o{dest_dir}", "-y"], check=True)
                else:
                    raise Exception("Para archivos .7z instale py7zr: pip install py7zr")
        else:
            raise Exception(f"Unsupported format: {ext}")

    def extract_archive(self, archive_path, dest_dir):
        """Extracción recursiva — desempaca RARs dentro de RARs hasta que no quede nada comprimido."""
        COMPRESSED_EXTS = {".rar", ".zip", ".7z"}
        MAX_DEPTH = 6  # seguridad contra loops infinitos

        # Extraer el archivo raíz
        self.extract_single(archive_path, dest_dir)

        # Buscar y extraer recursivamente cualquier comprimido adentro
        for depth in range(MAX_DEPTH):
            found_any = False
            for root, dirs, files in os.walk(dest_dir):
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in COMPRESSED_EXTS:
                        nested_path = os.path.join(root, f)
                        nested_dest = os.path.join(root, os.path.splitext(f)[0])
                        os.makedirs(nested_dest, exist_ok=True)
                        try:
                            self.extract_single(nested_path, nested_dest)
                            os.remove(nested_path)  # eliminar el comprimido ya extraído
                            found_any = True
                        except Exception:
                            pass  # si falla uno, continúa con los demás
            if not found_any:
                break  # no quedaron más comprimidos, listo

    def import_logic(self, source_path, import_type):
        temp_dir = os.path.join(os.environ["TEMP"], "nfs_work_dir")
        try:
            if import_type == "rar":
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                os.makedirs(temp_dir)
                self.extract_archive(source_path, temp_dir)
                work_path = temp_dir
            elif import_type == "rar_extracted":
                work_path = source_path
            else:
                work_path = source_path

            car_folder_src, car_name, bins_to_move = None, "Not detected", []

            # ── Señales de carpeta de auto ────────────────────────────────
            CAR_SIGNALS_BASE = {"geometry", "car", "fe", "attributes", "vinyls",
                                "colors", "damage", "textures", "secondarylogo"}

            def is_manufacturer_bin(filename):
                base = os.path.splitext(filename)[0]
                return base[0].isdigit() if base else False

            def is_car_folder(files):
                bases = {os.path.splitext(f)[0].lower() for f in files}
                return "geometry" in bases or len(CAR_SIGNALS_BASE & bases) >= 2

            # ── Búsqueda exhaustiva en TODO el árbol extraído ─────────────
            # No importa cuántos niveles de carpetas haya — busca en todos
            for root, dirs, files in os.walk(work_path):
                root_upper = root.upper().replace(os.sep, "/")
                in_frontend = any(p in root_upper for p in ["FRONTEND", "MANUFACTURERS"])

                # Prioridad 1: estructura CARS_REPLACE ya organizada
                if ("CARS_REPLACE" in root_upper or "CARS REPLACE" in root_upper) and not in_frontend:
                    for d in sorted(dirs):
                        candidate = os.path.join(root, d)
                        if os.path.isdir(candidate):
                            car_folder_src = candidate
                            car_name = d
                            break

                # Prioridad 2: carpeta con señales de auto
                if car_folder_src is None and not in_frontend and is_car_folder(files):
                    car_folder_src = root
                    car_name = os.path.basename(root)

                # BINs de fabricante — en cualquier nivel
                for f in files:
                    if f.lower().endswith(".bin") and is_manufacturer_bin(f):
                        if os.path.join(root, f) not in bins_to_move:
                            bins_to_move.append(os.path.join(root, f))

            if car_folder_src or bins_to_move:
                bin_labels = ", ".join(os.path.basename(x) for x in bins_to_move) if bins_to_move else "None"

                # ── Vista previa antes de instalar ───────────────────────
                _dest_check = os.path.join(self.addons_path, "CARS_REPLACE", car_name)
                _will_replace = os.path.exists(_dest_check)
                preview = ModPreviewDialog(self, car_name, bin_labels, self.lang, _will_replace, self.theme)
                if not preview.exec():
                    return  # Usuario canceló

                nickname = self.ask_car_nickname(car_name, bin_labels)
                print(f"DEBUG nickname='{nickname}' type={type(nickname)}")

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

                self.add_to_history(car_name, bin_labels, nickname)
                self.save_history_to_disk(car_name, bin_labels, nickname)
                self.themed_msg("Done" if self.lang == "EN" else "Listo", f"{self.texts[self.lang]['mod_installed']} {car_name}.\nBINs: {bin_labels}", "info")
            else:
                if import_type in ("rar", "rar_extracted"):
                    ExtractHintDialog(self, self.lang, self.theme).exec()
                else:
                    FolderHintDialog(self, self.lang, self.theme).exec()

        except Exception:
            if import_type in ("rar", "rar_extracted"):
                ExtractHintDialog(self, self.lang, self.theme).exec()
            else:
                FolderHintDialog(self, self.lang, self.theme).exec()
        finally:
            if import_type in ("rar", "rar_extracted") and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    # ── Historial ────────────────────────────────────────────────────────

    def themed_msg(self, title, msg, icon="info"):
        """QMessageBox con el tema elegido."""
        t = THEMES[self.theme]; a = t["accent"]; ar = t["accent_rgba"]; pb = t["panel_bg"]
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setFixedWidth(380)
        dlg.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.MSWindowsFixedSizeDialogHint)
        dlg.setStyleSheet(f"QDialog {{ background-color: {pb}; }}")
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(35, 25, 35, 25)
        lay.setSpacing(14)
        icon_map = {"info": "✓", "error": "✕", "warn": "⚠"}
        icon_color = {"info": a, "error": "#E74C3C", "warn": "#E67E22"}
        lbl_icon = QLabel(icon_map.get(icon, "✓"))
        lbl_icon.setStyleSheet(f"color: {icon_color.get(icon, a)}; font-size: 24px; background: transparent;")
        lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl_icon)
        lbl_msg = QLabel(msg)
        lbl_msg.setStyleSheet("color: rgba(255,255,255,0.85); font-size: 11px; background: transparent;")
        lbl_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_msg.setWordWrap(True)
        lay.addWidget(lbl_msg)
        lay.addStretch()
        btn = QPushButton("OK")
        btn.setFixedHeight(36)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"QPushButton {{ background: rgba({ar},0.1); color: {a}; border: 1px solid rgba({ar},0.4); border-radius: 4px; font-weight: bold; }} QPushButton:hover {{ background: {a}; color: white; }}")
        btn.clicked.connect(dlg.accept)
        lay.addWidget(btn)
        dlg.adjustSize()
        dlg.exec()

    def ask_car_nickname(self, car_name, bin_labels):
        """Pide al usuario el nombre del carro a reemplazar."""
        t = THEMES[self.theme]
        a = t["accent"]
        ar = t["accent_rgba"]
        pb = t["panel_bg"]

        dlg = QDialog(self)
        title_text = "IMPORT" if self.lang == "EN" else "IMPORTAR"
        dlg.setWindowTitle(title_text.lower())
        dlg.setFixedSize(380, 260)
        dlg.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.MSWindowsFixedSizeDialogHint)
        dlg.setStyleSheet(f"QDialog {{ background-color: {pb}; }}")

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(35, 30, 35, 30)
        lay.setSpacing(14)

        lbl_title = QLabel(title_text)
        lbl_title.setStyleSheet(f"color: {a}; font-size: 13px; font-weight: bold; letter-spacing: 2px;")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl_title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background: rgba({ar},0.3); border: none;")
        sep.setFixedHeight(1)
        lay.addWidget(sep)

        prompt = "Write the name of the model to import" if self.lang == "EN" else "Escriba el nombre del modelo a importar"
        lbl_prompt = QLabel(prompt)
        lbl_prompt.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 10px;")
        lbl_prompt.setWordWrap(True)
        lay.addWidget(lbl_prompt)

        field = QLineEdit()
        field.setFixedHeight(34)
        ex = "Example: Skyline R33" if self.lang == "EN" else "Ejemplo: Skyline R33"
        field.setPlaceholderText(ex)
        field.setStyleSheet(f"QLineEdit {{ background: rgba(255,255,255,0.04); border: 1px solid rgba({ar},0.3); border-radius: 4px; color: white; font-size: 12px; padding: 4px 10px; }} QLineEdit:focus {{ border: 1px solid rgba({ar},0.7); }}")
        lay.addWidget(field)

        lay.addStretch()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_cancel = QPushButton("CANCEL" if self.lang == "EN" else "CANCELAR")
        btn_ok = QPushButton("OK")
        for b in [btn_cancel, btn_ok]:
            b.setFixedHeight(36)
            b.setCursor(Qt.CursorShape.PointingHandCursor)

        btn_cancel.setStyleSheet(f"QPushButton {{ background: transparent; color: rgba(255,255,255,0.4); border: 1px solid rgba(255,255,255,0.1); border-radius: 4px; font-weight: bold; }} QPushButton:hover {{ color: white; border-color: rgba(255,255,255,0.4); }}")
        btn_ok.setStyleSheet(f"QPushButton {{ background: rgba({ar},0.1); color: {a}; border: 1px solid rgba({ar},0.4); border-radius: 4px; font-weight: bold; }} QPushButton:hover {{ background: rgba({ar},0.2); color: white; }}")

        btn_cancel.clicked.connect(dlg.reject)
        btn_ok.clicked.connect(dlg.accept)
        field.returnPressed.connect(dlg.accept)

        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        lay.addLayout(btn_row)

        dlg.raise_()
        dlg.activateWindow()
        field.setFocus()
        dlg.exec()
        return field.text().strip() or None

    def add_to_history(self, car_name, bin_names, nickname=None):
        item = QListWidgetItem(self.list_history)
        widget = QWidget()
        lay = QHBoxLayout(widget)
        lay.setContentsMargins(5, 5, 5, 5)
        nick = (nickname or "").strip()
        display = f"{car_name.upper()} ({nick.upper()})" if nick else car_name.upper()
        txt = QLabel(f"MOD: {display}\nBIN: {bin_names}")
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

    def save_history_to_disk(self, car, bins, nickname=None):
        data = []
        if os.path.exists(self.history_file):
            with open(self.history_file, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                except:
                    data = []
        if not any(d["car"] == car for d in data):
            entry = {"car": car, "bins": bins}
            if nickname: entry["nickname"] = nickname
            data.append(entry)
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    def load_persistent_history(self):
        if os.path.exists(self.history_file):
            with open(self.history_file, "r", encoding="utf-8") as f:
                try:
                    for entry in json.load(f):
                        self.add_to_history(entry["car"], entry["bins"], entry.get("nickname"))
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
        t = THEMES[self.theme]
        a = t["accent"]; ar = t["accent_rgba"]; pb = t["panel_bg"]
        search_style = f"QLineEdit {{ background: rgba(255,255,255,0.04); border: 1px solid rgba({ar},0.2); border-radius: 4px; color: rgba(255,255,255,0.7); font-size: 10px; padding: 4px 8px; }} QLineEdit:focus {{ border: 1px solid rgba({ar},0.6); color: white; }}"

        self.ventana_bib = QWidget(self)
        self.ventana_bib.setWindowTitle("Library")
        self.ventana_bib.setFixedSize(500, 650)
        self.ventana_bib.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.MSWindowsFixedSizeDialogHint
        )
        self.ventana_bib.setStyleSheet(f"QWidget {{ background-color: {pb}; }}")
        layout_bib = QVBoxLayout(self.ventana_bib)
        layout_bib.setContentsMargins(30, 30, 30, 30)
        layout_bib.setSpacing(10)

        title_lib = QLabel("GARAGE REPOSITORY" if self.lang == "EN" else "REPOSITORIO")
        title_lib.setStyleSheet(f"color: {a}; font-size: 16px; font-weight: bold; letter-spacing: 2px; margin-bottom: 20px;")
        title_lib.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout_bib.addWidget(title_lib)

        self.lbl_lib_models = QLabel()
        self.lbl_lib_models.setStyleSheet(f"color: rgba({ar},0.5); font-weight: bold; font-size: 10px; margin-left: 5px;")
        layout_bib.addWidget(self.lbl_lib_models)

        self.search_cars = QLineEdit()
        self.search_cars.setFixedHeight(28)
        self.search_cars.setStyleSheet(search_style)
        self.search_cars.setPlaceholderText("Buscar carpeta" if self.lang == "ES" else "Search folder")
        self.search_cars.textChanged.connect(self._filter_cars)
        layout_bib.addWidget(self.search_cars)

        self.list_cars = QListWidget()
        self.list_cars.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list_cars.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._apply_list_style(self.list_cars)
        layout_bib.addWidget(self.list_cars)

        self.lbl_lib_bins = QLabel()
        self.lbl_lib_bins.setStyleSheet(f"color: rgba({ar},0.5); font-weight: bold; font-size: 10px; margin-left: 5px;")
        layout_bib.addWidget(self.lbl_lib_bins)

        self.search_bins = QLineEdit()
        self.search_bins.setFixedHeight(28)
        self.search_bins.setStyleSheet(search_style)
        self.search_bins.setPlaceholderText("Buscar BIN" if self.lang == "ES" else "Search BIN")
        self.search_bins.textChanged.connect(self._filter_bins)
        layout_bib.addWidget(self.search_bins)

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
                background: rgba({ar},0.35);
                border-radius: 2px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba({ar},0.7);
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

    def _filter_cars(self, text):
        for i in range(self.list_cars.count()):
            item = self.list_cars.item(i)
            w = self.list_cars.itemWidget(item)
            label = w.findChild(QLabel) if w else None
            name = label.text() if label else ""
            item.setHidden(text.upper() not in name.upper())

    def _filter_bins(self, text):
        for i in range(self.list_bins.count()):
            item = self.list_bins.item(i)
            w = self.list_bins.itemWidget(item)
            label = w.findChild(QLabel) if w else None
            name = label.text() if label else ""
            item.setHidden(text.upper() not in name.upper())

    def _filter_history(self, text):
        for i in range(self.list_history.count()):
            item = self.list_history.item(i)
            w = self.list_history.itemWidget(item)
            label = w.findChild(QLabel) if w else None
            name = label.text() if label else ""
            item.setHidden(text.upper() not in name.upper())

    def load_library_data(self):
        self.list_cars.clear()
        self.list_bins.clear()

        # Cargar nicknames del historial
        nickname_map = {}
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    for entry in json.load(f):
                        if entry.get("nickname"):
                            nickname_map[entry["car"].upper()] = entry["nickname"]
            except:
                pass

        cars_active = cars_inactive = 0
        bins_active = bins_inactive = 0

        for folder, active in [
            (os.path.join(self.addons_path,   "CARS_REPLACE"), True),
            (os.path.join(self.disabled_path, "CARS"),         False),
        ]:
            if os.path.exists(folder):
                for d in sorted(os.listdir(folder)):
                    if os.path.isdir(os.path.join(folder, d)):
                        nick = nickname_map.get(d.upper())
                        self.create_library_item(self.list_cars, d, "car", active, nick)
                        if active: cars_active += 1
                        else: cars_inactive += 1

        for folder, active in [
            (os.path.join(self.addons_path,   "FRONTEND", "MANUFACTURERS"), True),
            (os.path.join(self.disabled_path, "BINS"),                      False),
        ]:
            if os.path.exists(folder):
                for f in sorted(os.listdir(folder)):
                    if f.lower().endswith(".bin"):
                        self.create_library_item(self.list_bins, f, "bin", active, None)
                        if active: bins_active += 1
                        else: bins_inactive += 1

        # Actualizar conteos en los labels
        t = self.texts[self.lang]
        self.lbl_lib_models.setText(
            f"{t['lib_models']}    "
            f"<span style='color:rgba(255,255,255,0.35); font-weight:normal;'>"
            f"{cars_active} active · {cars_inactive} inactive</span>"
        )
        self.lbl_lib_models.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_lib_bins.setText(
            f"{t['lib_bins']}    "
            f"<span style='color:rgba(255,255,255,0.35); font-weight:normal;'>"
            f"{bins_active} active · {bins_inactive} inactive</span>"
        )
        self.lbl_lib_bins.setTextFormat(Qt.TextFormat.RichText)

    def create_library_item(self, list_widget, name, item_type, active, nickname=None):
        item = QListWidgetItem(list_widget)
        widget = QWidget()
        lay = QHBoxLayout(widget)
        lay.setContentsMargins(5, 5, 5, 5)
        a = THEMES[self.theme]["accent"]
        color = a if active else "rgba(255,255,255,0.3)"
        nick = (nickname or "").strip()
        display = f"{name.upper()} ({nick.upper()})" if nick else name.upper()
        txt = QLabel(display)
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
            self.themed_msg("Error", str(e), "error")

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
            except Exception:
                ExtractHintDialog(self, self.lang, self.theme).exec()
            # También mostrar hint si no se detectó contenido válido


# ── Entry point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        # Si ya viene el idioma como argumento (relanzado como admin), usarlo directo
        selected_lang = "ES"
        for arg in sys.argv[1:]:
            if arg.startswith("--lang="):
                selected_lang = arg.split("=")[1]
                break
        gui = ModLoaderGUI(initial_lang=selected_lang)
        gui.show()
        sys.exit(app.exec())
    except Exception as e:
        import traceback
        log_path = r"C:\Users\jonat\OneDrive\Desktop\crash.log"
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
        ctypes.windll.user32.MessageBoxW(0, f"Error Crítico: {str(e)}\n\nLog guardado en: {log_path}", "NFS Garage Crash", 0x10)

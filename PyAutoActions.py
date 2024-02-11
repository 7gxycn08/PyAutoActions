import time
import threading
import subprocess
from PyQt6.QtWidgets import (QMenu, QSystemTrayIcon, QApplication, QVBoxLayout, QListWidget, QPushButton,
                             QFileDialog, QMainWindow, QWidget, QMessageBox, QHBoxLayout, QListWidgetItem)
from PyQt6.QtGui import QIcon, QAction, QPixmap, QImage
from PyQt6.QtCore import QCoreApplication, QSettings, pyqtSignal, Qt, QSize
import sys
import os
import configparser
import ctypes
import win32com.client
from PIL import Image
import io


class ProcessMonitor(QWidget):
    finished = pyqtSignal()

    def __init__(self, process_list, toggle_state, use_alternative_hdr):
        super().__init__()
        self.count = None
        self.shutting_down = False
        self.manual_hdr = None
        self.process_check_status = None
        self.exception_msg = None
        self.finished.connect(self.on_finished_show_msg, Qt.ConnectionType.QueuedConnection)

        self.error_thread = None
        self.process_thread = None
        self.enable_hdr_thread = None
        self.disable_hdr_thread = None

        self.use_alternative_hdr = use_alternative_hdr
        self.process_list = process_list
        self.toggle_state = toggle_state

        self.found_process = False
        self.main_process = None

        self.my_dll = ctypes.CDLL(r"Dependency\HDRSwitch.dll")
        self.SetGlobalHDRState = self.my_dll.SetGlobalHDRState
        self.SetGlobalHDRState.argtypes = [ctypes.c_bool]
        self.SetGlobalHDRState.restype = None
        self.SetGlobalHDRState.__cdecl__ = True

    def process_monitor(self):
        while not self.shutting_down:
            try:
                if self.manual_hdr and self.count:
                    time.sleep(20)
                    self.count = False

                if self.process_check_status:
                    break

                if not self.found_process:
                    self.process_thread = threading.Thread(target=self.process_check, daemon=True)
                    self.process_thread.start()
                else:
                    if self.toggle_state and not self.is_process_running(self.main_process):
                        self.toggle_state = False
                        self.found_process = False
                        self.manual_hdr = False
                        self.call_set_global_hdr_state()

                time.sleep(5)
            except RuntimeError:
                break
            except Exception as e:
                self.exception_msg = f"process_monitor: {e}"
                self.finished.emit()
                break

    def process_check(self):
        try:
            for process in self.process_list:
                if self.is_process_running(process):
                    if not self.toggle_state:
                        self.toggle_state = True
                        self.found_process = True
                        self.main_process = process
                        self.enable_hdr_thread = threading.Thread(
                            target=self.call_set_global_hdr_state, daemon=True)
                        self.enable_hdr_thread.start()
                        self.enable_hdr_thread.join()
                        break

        except Exception as e:
            self.process_check_status = True
            self.exception_msg = f"process_check: {e}"
            self.finished.emit()
            return

    def is_process_running(self, process_name):
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

        try:
            processes = (ctypes.c_ulong * 2048)()
            cb = ctypes.c_ulong(ctypes.sizeof(processes))
            ctypes.windll.psapi.EnumProcesses(ctypes.byref(processes), cb, ctypes.byref(cb))

            process_count = cb.value // ctypes.sizeof(ctypes.c_ulong)
            for i in range(process_count):
                process_id = processes[i]
                process_handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False,
                                                                    process_id)

                if process_handle:
                    buffer_size = 260
                    buffer = ctypes.create_unicode_buffer(buffer_size)
                    success = ctypes.windll.kernel32.QueryFullProcessImageNameW(process_handle, 0, buffer,
                                                                                ctypes.byref(
                                                                                    ctypes.c_ulong(buffer_size)))
                    ctypes.windll.kernel32.CloseHandle(process_handle)

                    if success:
                        process_name_actual = os.path.basename(buffer.value)
                        if process_name_actual == process_name:
                            return True
            return False

        except Exception as e:
            self.exception_msg = f"is_process_running {e}"
            self.finished.emit()
            return False

    def call_set_global_hdr_state(self):
        try:
            self.SetGlobalHDRState(bool(self.toggle_state))
        except Exception as e:
            self.exception_msg = f"call_set_global_hdr_state: {e}"
            self.finished.emit()

    def on_finished_show_msg(self):
        warning_message_box = QMessageBox()
        warning_message_box.setWindowTitle("PyAutoActions Error")
        warning_message_box.setWindowIcon(QIcon("Resources/main.ico"))
        warning_message_box.setFixedSize(400, 200)
        warning_message_box.setIcon(QMessageBox.Icon.Critical)
        warning_message_box.setText(f"{self.exception_msg}")
        warning_message_box.exec()


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint),
                ("biWidth", ctypes.c_int),
                ("biHeight", ctypes.c_int),
                ("biPlanes", ctypes.c_ushort),
                ("biBitCount", ctypes.c_ushort),
                ("biCompression", ctypes.c_uint),
                ("biSizeImage", ctypes.c_uint),
                ("biXPelsPerMeter", ctypes.c_int),
                ("biYPelsPerMeter", ctypes.c_int),
                ("biClrUsed", ctypes.c_uint),
                ("biClrImportant", ctypes.c_uint)]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("7gxycn08@Github", "PyAutoActions")
        self.ICON_SIZE = 64
        self.action_names = []
        self.use_alternative_hdr = None
        self.monitor_thread = None
        self.boot_status = None
        self.toggle_state = False
        self.script_path = f"{os.path.abspath(sys.argv[0])}"
        self.task_name = "PyAutoActions"
        self.config = configparser.ConfigParser()
        self.config.read(r'Dependency\processlist.ini')
        self.list_str = self.config['HDR_APPS']['processes']
        self.process_list = self.list_str.split(', ') if self.list_str else []

        self.warning_message_box = QMessageBox(self)
        self.warning_message_box.setIcon(QMessageBox.Icon.Warning)
        self.warning_message_box.setWindowTitle("PyAutoActions Error")
        self.warning_message_box.setWindowIcon(QIcon(r"Resources/main.ico"))
        self.warning_message_box.setFixedSize(400, 200)

        self.setWindowTitle("PyAutoActions v1.0.0.7")
        self.setWindowIcon(QIcon(os.path.abspath(r"Resources/main.ico")))
        self.setGeometry(100, 100, 600, 400)

        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)

        self.list_widget = QListWidget()

        self.add_button = QPushButton('Add Application')
        self.add_button.setFixedSize(150, 25)
        self.add_button_layout = QHBoxLayout()
        self.add_button_layout.addStretch()
        self.add_button_layout.addWidget(self.add_button)
        self.add_button_layout.addStretch()

        self.remove_button = QPushButton('Remove Selected Application')
        self.remove_button.setFixedSize(180, 25)
        self.remove_button_layout = QHBoxLayout()
        self.remove_button_layout.addStretch()
        self.remove_button_layout.addWidget(self.remove_button)
        self.remove_button_layout.addStretch()

        layout = QVBoxLayout()
        layout.addWidget(self.list_widget)
        layout.addLayout(self.add_button_layout)
        layout.addLayout(self.remove_button_layout)

        self.central_widget.setLayout(layout)

        self.add_button.clicked.connect(self.add_exe)
        self.remove_button.clicked.connect(self.remove_selected_entry)
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setToolTip("PyAutoActions")
        self.tray_icon.setIcon(QIcon(os.path.abspath(r"Resources/main.ico")))
        self.tray_icon.activated.connect(self.tray_icon_activated)

        self.menu = QMenu(self)
        self.menu.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.menu.setWindowFlags(self.menu.windowFlags() | Qt.WindowType.FramelessWindowHint)

        self.submenu = QMenu('Game Launcher', self.menu)
        self.submenu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.submenu.setWindowFlags(self.menu.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self.submenu.setIcon(QIcon(r"Resources/main.ico"))
        self.menu.addMenu(self.submenu)
        self.menu.addSeparator()

        self.start_hidden_action = QAction('Start In Tray', self.menu)
        self.start_hidden_action.setCheckable(True)
        self.start_hidden_action.setChecked(self.settings.value("start_hidden", type=bool))
        self.start_hidden_action.triggered.connect(self.toggle_start_hidden)
        self.menu.addAction(self.start_hidden_action)

        self.run_on_boot_action = QAction('Run on System Boot', self.menu)
        self.run_on_boot_action.setCheckable(True)
        self.run_on_boot_action.setChecked(self.settings.value("run_on_boot", type=bool))
        self.run_on_boot_action.triggered.connect(self.run_on_boot)
        self.menu.addAction(self.run_on_boot_action)

        about_button = self.menu.addAction(QIcon(r"Resources\about.ico"), 'About')
        about_button.triggered.connect(self.about_page)
        action_exit = self.menu.addAction(QIcon(r"Resources\exit.ico"), 'Exit')
        action_exit.triggered.connect(self.close_tray_icon)
        self.menu.addAction(action_exit)
        start_hidden_checked = self.settings.value("start_hidden", type=bool)
        self.start_hidden_action.setChecked(start_hidden_checked)
        self.tray_icon.setContextMenu(self.menu)
        if start_hidden_checked:
            self.hide()
        else:
            self.show()
        self.tray_icon.show()
        self.monitor = ProcessMonitor(self.process_list, self.toggle_state, self.use_alternative_hdr)
        self.monitor_thread = threading.Thread(target=self.monitor.process_monitor)
        self.monitor_thread.start()
        self.load_processes_from_config()
        self.create_actions()

    def extract_icon(self, file_path, icon_index=0):
        try:
            icon_handle = ctypes.windll.shell32.ExtractIconW(0, file_path, icon_index)
            if icon_handle <= 1:
                return None
        except Exception as e:
            self.warning_message_box.warning(self, "PyAutoActions Error", f"extract_icon: {e}",
                                             QMessageBox.StandardButton.Ok)
            return None

        return icon_handle

    def get_icon_as_image_object(self, file_path, icon_index=0):
        BI_RGB = 0
        DIB_RGB_COLORS = 0

        icon_handle = self.extract_icon(file_path, icon_index)
        if icon_handle:
            hdc = ctypes.windll.user32.GetDC(0)
            mem_dc = ctypes.windll.gdi32.CreateCompatibleDC(hdc)
            bitmap = ctypes.windll.gdi32.CreateCompatibleBitmap(hdc, self.ICON_SIZE, self.ICON_SIZE)
            ctypes.windll.gdi32.SelectObject(mem_dc, bitmap)

            ctypes.windll.user32.DrawIconEx(
                mem_dc, 0, 0, icon_handle, self.ICON_SIZE, self.ICON_SIZE, 0, None, 0x0003 | 0x0008
            )

            bmp_header = BITMAPINFOHEADER()
            bmp_header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmp_header.biWidth = self.ICON_SIZE
            bmp_header.biHeight = -self.ICON_SIZE
            bmp_header.biPlanes = 1
            bmp_header.biBitCount = 32
            bmp_header.biCompression = BI_RGB

            bmp_str = ctypes.create_string_buffer(self.ICON_SIZE * self.ICON_SIZE * 4)
            ctypes.windll.gdi32.GetDIBits(mem_dc, bitmap, 0, self.ICON_SIZE, bmp_str, ctypes.byref(bmp_header),
                                          DIB_RGB_COLORS)

            im = Image.frombuffer(
                'RGBA',
                (self.ICON_SIZE, self.ICON_SIZE),
                bmp_str, 'raw', 'BGRA', 0, 1)

            ctypes.windll.user32.DestroyIcon(icon_handle)
            ctypes.windll.gdi32.DeleteObject(bitmap)
            ctypes.windll.gdi32.DeleteDC(mem_dc)
            ctypes.windll.user32.ReleaseDC(0, hdc)

            return im
        else:
            self.warning_message_box.warning(self, "PyAutoActions Error",
                                             "get_icon_as_image_object: Failed to get image object",
                                             QMessageBox.StandardButton.Ok)
            return None

    def resize_pixmap(self, pixmap, width, height):
        new_size = QSize(width, height)
        return pixmap.scaled(new_size, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)

    def pil_image_to_qicon(self, image_object):
        byte_array = io.BytesIO()
        image_object.save(byte_array, format='PNG')
        qimage = QImage()
        qimage.loadFromData(byte_array.getvalue())

        qpixmap = QPixmap.fromImage(qimage)
        resized_pixmap = self.resize_pixmap(qpixmap, 32, 32)
        return QIcon(resized_pixmap)

    def delete_submenu_action(self, index):
        if self.submenu.actions():
            item_to_delete = self.submenu.actions()[index]
            self.submenu.removeAction(item_to_delete)

    def create_actions(self):
        try:
            list_widget_items = [self.list_widget.item(i).text() for i in range(self.list_widget.count()) if
                                 self.list_widget.item(i).text()]
            unique_items_set = set()
            self.submenu.clear()

            if not list_widget_items:
                empty_action = QAction("Empty", self.menu)
                empty_action.setEnabled(False)
                self.submenu.addAction(empty_action)
                return
            else:
                for item_text in list_widget_items:
                    if item_text not in unique_items_set:
                        base_name = os.path.basename(item_text).rstrip(".exe")
                        image_object = self.get_icon_as_image_object(item_text)
                        icon = self.pil_image_to_qicon(image_object)
                        pixmap_icon = QIcon(icon)
                        new_action = QAction(pixmap_icon, base_name, self.menu)
                        new_action.triggered.connect(lambda checked, p=item_text: self.on_action_triggered(p))
                        self.submenu.addAction(new_action)
                        unique_items_set.add(item_text)

        except Exception as e:
            self.warning_message_box.warning(self, "PyAutoActions Error", f"create_actions: {e}",
                                             QMessageBox.StandardButton.Ok)

    def run_as_admin(self, executable_path):
        try:
            folder_path = os.path.dirname(executable_path)

            ctypes.windll.shell32.ShellExecuteW(None, "runas", executable_path, None, folder_path, 1)
        except Exception as e:
            self.warning_message_box.warning(self, "PyAutoActions Error", f"run_as_admin: {e}",
                                             QMessageBox.StandardButton.Ok)

    def on_action_triggered(self, path):
        try:
            self.monitor.main_process = os.path.basename(path)
            self.monitor.found_process = True
            self.monitor.toggle_state = True
            self.monitor.manual_hdr = True
            self.monitor.count = True
            self.monitor.call_set_global_hdr_state()
            threading.Thread(target=lambda: self.run_as_admin(path), daemon=True).start()
        except Exception as e:
            self.warning_message_box.warning(self, "PyAutoActions Error", f"on_action_triggered: {e}",
                                             QMessageBox.StandardButton.Ok)

    def update_classes_variables(self):
        self.monitor.toggle_state = self.toggle_state
        self.monitor.process_list = self.process_list

    def run_on_boot(self):
        checked = self.run_on_boot_action.isChecked()
        self.settings.setValue("run_on_boot", checked)
        state = self.settings.value("run_on_boot", type=bool)
        if state:
            self.register_as_task()
        else:
            self.remove_task()

    def remove_task(self):
        if self.is_task_installed():
            try:
                scheduler = win32com.client.Dispatch('Schedule.Service')
                scheduler.Connect()

                root_folder = scheduler.GetFolder('\\')
                task = root_folder.GetTask(self.task_name)

                root_folder.DeleteTask(self.task_name, 0)

            except Exception as e:
                self.warning_message_box.warning(self, "PyAutoActions Error", f"remove_task: {e}",
                                                 QMessageBox.StandardButton.Ok)

    def toggle_start_hidden(self):
        checked = self.start_hidden_action.isChecked()
        self.settings.setValue("start_hidden", checked)

    def is_task_installed(self):
        try:
            scheduler = win32com.client.Dispatch('Schedule.Service')
            scheduler.Connect()

            root_folder = scheduler.GetFolder('\\')

            try:
                task = root_folder.GetTask(self.task_name)
                return True
            except:
                return False
        except Exception as e:
            self.warning_message_box.warning(self, "PyAutoActions Error", f"is_task_installed: {e}",
                                             QMessageBox.StandardButton.Ok)

    def register_as_task(self):
        if not self.is_task_installed():
            try:
                scheduler = win32com.client.Dispatch('Schedule.Service')
                scheduler.Connect()

                rootFolder = scheduler.GetFolder('\\')

                taskDef = scheduler.NewTask(0)
                taskDef.RegistrationInfo.Description = 'Start PyAutoActions at Boot'

                trigger = taskDef.Triggers.Create(9)
                trigger.Id = 'LogonTriggerId'

                execAction = taskDef.Actions.Create(0)
                execAction.Path = self.script_path
                execAction.WorkingDirectory = os.getcwd()

                principal = taskDef.Principal
                principal.UserId = os.getlogin()
                principal.RunLevel = 1
                principal.LogonType = 3

                taskDef.Settings.ExecutionTimeLimit = 'PT0S'

                rootFolder.RegisterTaskDefinition(
                    self.task_name,
                    taskDef,
                    6,
                    None,
                    None,
                    3
                )
            except Exception as e:
                self.warning_message_box.warning(self, "PyAutoActions Error", f"register_as_task: {e}",
                                                 QMessageBox.StandardButton.Ok)

    def about_page(self):
        subprocess.Popen("start https://github.com/7gxycn08/PyAutoActions",
                         shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)

    def closeEvent(self, event):
        event.ignore()
        self.hide()

    def tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_window()

    def close_tray_icon(self):
        self.monitor.shutting_down = True
        QCoreApplication.quit()

    def show_window(self):
        self.show()
        self.activateWindow()

    def remove_selected_entry(self):
        try:
            selected_item = self.list_widget.currentItem()

            if selected_item is not None and selected_item.text().strip():
                selected_text = selected_item.text()
                exe_index_to_remove = self.process_list.index(selected_text)
                self.delete_submenu_action(exe_index_to_remove)
                self.process_list.pop(exe_index_to_remove)
                self.save_config()
                self.list_widget.takeItem(self.list_widget.row(selected_item))
                self.create_actions()
                self.update_classes_variables()
            else:
                self.warning_message_box.warning(self, "PyAutoActions Error", "Nothing to remove.",
                                                 QMessageBox.StandardButton.Ok)
        except ValueError as ve:
            self.warning_message_box.warning(self, f"PyAutoActions Error:", {ve}, QMessageBox.StandardButton.Ok)
        except Exception as e:
            self.warning_message_box.warning(self, "PyAutoActions Error", f"Nothing to remove. {e}",
                                             QMessageBox.StandardButton.Ok)

    def add_exe(self):
        try:
            file_dialog = QFileDialog()
            file_path, _ = file_dialog.getOpenFileName(self, "Select Executable", "", "Executable Files (*.exe)")
            if file_path:
                exe_path = os.path.abspath(file_path)
                if exe_path in self.process_list:

                    self.warning_message_box.warning(self, "PyAutoActions Error",
                                                     f"Process {exe_path} already exists in the list.",
                                                     QMessageBox.StandardButton.Ok)
                else:
                    icon = self.get_icon_as_image_object(exe_path)
                    q_icon = self.pil_image_to_qicon(icon)
                    list_item = QListWidgetItem()
                    list_item.setIcon(q_icon)
                    list_item.setText(exe_path)
                    self.list_widget.addItem(list_item)
                    self.create_actions()
                    self.process_list.append(exe_path)
                    threading.Thread(target=self.save_config, daemon=True).start()
                    self.update_classes_variables()
        except Exception as e:
            self.warning_message_box.warning(self, "PyAutoActions Error", f"add_exe: {e}",
                                             QMessageBox.StandardButton.Ok)

    def save_config(self):
        try:
            self.list_str = ', '.join(self.process_list)
            self.config['HDR_APPS']['processes'] = self.list_str

            with open(r'Dependency\processlist.ini', 'w') as configfile:
                self.config.write(configfile)
                self.update_classes_variables()
        except Exception as e:
            self.warning_message_box.warning(self, "PyAutoActions Error", f"save_config: {e}",
                                             QMessageBox.StandardButton.Ok)

    def load_processes_from_config(self):
        try:
            self.list_widget.clear()
            self.config.read(r'Dependency\processlist.ini')
            if 'HDR_APPS' in self.config and 'processes' in self.config['HDR_APPS']:
                process_list_str = self.config['HDR_APPS']['processes']
                processes = process_list_str.split(', ')
                for process in processes:
                    if process:
                        icon = self.get_icon_as_image_object(process)
                        q_icon = self.pil_image_to_qicon(icon)
                        list_item = QListWidgetItem()
                        list_item.setIcon(q_icon)
                        list_item.setText(process)
                        self.list_widget.addItem(list_item)
                self.update_classes_variables()
        except Exception as e:
            self.warning_message_box.warning(self, "PyAutoActions Error", f"load_processes_from_config: {e}",
                                             QMessageBox.StandardButton.Ok)


if __name__ == "__main__":
    with open(r'Resources\custom.css', 'r') as file:
        stylesheet = file.read()
    app = QApplication(sys.argv)
    app.setStyleSheet(stylesheet)
    window = MainWindow()
    sys.exit(app.exec())

import ctypes
import time
import threading
from PyQt5.QtWidgets import (QMenu, QSystemTrayIcon,QApplication, QVBoxLayout, QListWidget, QPushButton,
                             QLineEdit,QFileDialog,QMainWindow,QWidget,QMessageBox,QAction)
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import QCoreApplication,QSettings
import sys
import os
import configparser
import subprocess

config = configparser.ConfigParser()
config.read('processlist.ini')

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010

my_dll = ctypes.CDLL(r"Dependancy\HDRSwitch.dll")
SetGlobalHDRState = my_dll.SetGlobalHDRState
SetGlobalHDRState.argtypes = [ctypes.c_bool]
SetGlobalHDRState.restype = None
SetGlobalHDRState.__cdecl__ = True

toggle_lock = threading.Lock()
list_str = config['HDR_APPS']['MyList']
process_list = list_str.split(', ') if list_str else []


class ProcessMonitor:
    def __init__(self):
        self.toggle_state = False
        self.found_process = False
        self.main_process = None

    def call_set_global_hdr_state(self,toggle_state):
        try:
            SetGlobalHDRState(bool(toggle_state))
        except Exception as e:
            QMessageBox.warning(None,f"Error calling SetGlobalHDRState: {e}",QMessageBox.Ok)

    def is_process_running(self,process_name):
        try:
            processes = (ctypes.c_ulong * 2048)()
            cb = ctypes.c_ulong(ctypes.sizeof(processes))
            ctypes.windll.psapi.EnumProcesses(ctypes.byref(processes), cb, ctypes.byref(cb))

            process_count = cb.value // ctypes.sizeof(ctypes.c_ulong)
            for i in range(process_count):
                process_id = processes[i]
                process_handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False,
                                                                    process_id)

                if process_handle:
                    buffer_size = 260
                    buffer = ctypes.create_unicode_buffer(buffer_size)
                    ctypes.windll.psapi.GetModuleBaseNameW(process_handle, 0, buffer, ctypes.sizeof(buffer))
                    process_name_actual = buffer.value.lower()
                    ctypes.windll.kernel32.CloseHandle(process_handle)
                    if process_name_actual == process_name.lower():
                        return True
            return False

        except Exception as e:
            QMessageBox.warning(self, "Error", f"An error occurred: {str(e)}", QMessageBox.Ok)

    def process_thread(self, process_list):
        for process in process_list:
            if self.is_process_running(process):
                if not self.toggle_state:
                    self.toggle_state = True
                    self.found_process = True
                    self.main_process = process
                    threading.Thread(
                        target=lambda: self.call_set_global_hdr_state(self.toggle_state), daemon=True).start()
                    break

    def process_monitor(self,process_list):
        while True:
            if not self.found_process:
                threading.Thread(target=lambda: self.process_thread(process_list), daemon=True).start()
            else:
                if self.toggle_state and not self.is_process_running(self.main_process):
                    self.toggle_state = False
                    self.found_process = False
                    threading.Thread(
                        target=lambda: self.call_set_global_hdr_state(self.toggle_state), daemon=True).start()
            time.sleep(5)
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.settings = QSettings("7gxycn08@Github", "PyAutoActions")
        self.setWindowTitle("PyAutoActions v1.0")
        self.setWindowIcon(QIcon(os.path.abspath("Resources/main.ico")))
        self.setGeometry(100, 100, 1000, 600)
        self.central_widget = QWidget(self)
        self.list_widget = QListWidget(self.central_widget)
        self.entry_line_edit = QLineEdit(self.central_widget)
        self.manual_add_button = QPushButton('Manual Add Entry', self.central_widget)
        self.add_button = QPushButton('Add Application', self.central_widget)
        self.remove_button = QPushButton('Remove Selected Application', self.central_widget)

        layout = QVBoxLayout(self.central_widget)
        layout.addWidget(self.list_widget)
        layout.addWidget(self.entry_line_edit)
        layout.addWidget(self.manual_add_button)
        layout.addWidget(self.add_button)
        layout.addWidget(self.remove_button)

        self.setCentralWidget(self.central_widget)
        self.manual_add_button.clicked.connect(self.add_entry)
        self.add_button.clicked.connect(self.add_exe)
        self.remove_button.clicked.connect(self.remove_entry)
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setToolTip("PyAutoActions")
        self.tray_icon.setIcon(QIcon(os.path.abspath("Resources/main.ico")))
        self.tray_icon.activated.connect(self.tray_icon_activated)
        self.show()
        self.load_processes_from_config()

        self.menu = QMenu()
        self.start_hidden_action = QAction('Start In Tray', self.menu)
        self.start_hidden_action.setCheckable(True)
        self.start_hidden_action.setChecked(self.settings.value("start_hidden", False, type=bool))
        self.start_hidden_action.triggered.connect(self.toggle_start_hidden)
        self.menu.addAction(self.start_hidden_action)
        about_button = self.menu.addAction(QIcon(fr"Resources\about.ico"),'About')
        about_button.triggered.connect(self.about_page)
        action_exit = self.menu.addAction(QIcon(fr"Resources\exit.ico"),'Exit')
        action_exit.triggered.connect(self.close_tray_icon)
        self.menu.addAction(action_exit)
        start_hidden_checked = self.settings.value("start_hidden", False, type=bool)
        self.start_hidden_action.setChecked(start_hidden_checked)
        self.tray_icon.setContextMenu(self.menu)
        if start_hidden_checked:
            self.hide()
        self.tray_icon.show()

    def toggle_start_hidden(self):
        checked = self.start_hidden_action.isChecked()
        self.settings.setValue("start_hidden", checked)

    def about_page(self):
        subprocess.Popen("start https://github.com/7gxycn08/PyAutoActions",
                         shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)

    def closeEvent(self, event):
        event.ignore()
        self.hide()
    def tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_window()
    def close_tray_icon(self):
        QCoreApplication.quit()

    def show_window(self):
        self.show()
        self.activateWindow()

    def add_entry(self):
        global process_list
        entry_text = self.entry_line_edit.text()
        if entry_text in process_list:
            QMessageBox.warning(self, "Error", f"Process '{entry_text}' already exists in the list.", QMessageBox.Ok)
        elif ".exe" not in entry_text:
            QMessageBox.warning(self, "Error", f"Manual Entries Require Extensions *.exe", QMessageBox.Ok)
        else:
            process_list.append(entry_text)
            self.save_config()
            if entry_text:
                self.list_widget.addItem(entry_text)
                self.entry_line_edit.clear()
    def remove_entry(self):
        selected_item = self.list_widget.currentItem()

        if selected_item:
            index_to_remove = process_list.index(selected_item.text())
            process_list.pop(index_to_remove)
            self.save_config()
            self.list_widget.takeItem(self.list_widget.row(selected_item))
    def add_exe(self):
        global process_list
        try:
            file_dialog = QFileDialog()
            file_path, _ = file_dialog.getOpenFileName(self, "Select Executable", "", "Executable Files (*.exe)")
            if file_path:
                exe_name = os.path.basename(file_path)
                if exe_name in process_list:
                    QMessageBox.warning(
                        self, "Error", f"Process '{exe_name}' already exists in the list.", QMessageBox.Ok)
                else:
                    self.list_widget.insertItem(0, exe_name)
                    process_list.append(exe_name)
                    threading.Thread(target=self.save_config, daemon=True).start()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"{e}", QMessageBox.Ok)

    def save_config(self):
        global config, process_list
        list_str = ', '.join(process_list)
        config['HDR_APPS'] = {'MyList': list_str}

        with open('processlist.ini', 'w') as configfile:
            config.write(configfile)
    def load_processes_from_config(self):
        self.list_widget.clear()
        config.read('processlist.ini')
        if 'HDR_APPS' in config and 'MyList' in config['HDR_APPS']:
            process_list_str = config['HDR_APPS']['MyList']
            processes = process_list_str.split(', ')
            for process in processes:
                self.list_widget.addItem(process)

if __name__ == "__main__":
    monitor = ProcessMonitor()
    threading.Thread(target=lambda: monitor.process_monitor(process_list),daemon=True).start()
    app = QApplication(sys.argv)
    window = MainWindow()
    sys.exit(app.exec_())

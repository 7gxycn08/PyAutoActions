import time
import threading
import tkinter.messagebox
import subprocess
from PyQt5.QtWidgets import (QMenu, QSystemTrayIcon,QApplication, QVBoxLayout, QListWidget, QPushButton,
                             QLineEdit,QFileDialog,QMainWindow,QWidget,QMessageBox,QAction)
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import QCoreApplication,QSettings
import sys
import os
import configparser
import ctypes
import win32com.client

class ProcessMonitor(QMainWindow):
    def __init__(self, process_list, toggle_state):
        super().__init__()
        self.process_list = process_list
        self.toggle_state = toggle_state
        self.found_process = False
        self.main_process = None
        self.my_dll = ctypes.CDLL(r"Dependancy\HDRSwitch.dll")
        self.SetGlobalHDRState = self.my_dll.SetGlobalHDRState
        self.SetGlobalHDRState.argtypes = [ctypes.c_bool]
        self.SetGlobalHDRState.restype = None
        self.SetGlobalHDRState.__cdecl__ = True

    def call_set_global_hdr_state(self):
        try:
            self.SetGlobalHDRState(bool(self.toggle_state))
        except Exception as e:
            tkinter.messagebox.showerror(title="Error", message=f"call_set_global_hdr_state: {e}")

    def is_process_running(self,process_name):
        PROCESS_QUERY_INFORMATION = 0x0400
        PROCESS_VM_READ = 0x0010
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
            tkinter.messagebox.showerror(title="Error", message=f"is_process_running: {e}")

    def process_thread(self):
        for process in self.process_list:
            if self.is_process_running(process):
                if not self.toggle_state:
                    self.toggle_state = True
                    self.found_process = True
                    self.main_process = process
                    threading.Thread(
                        target=self.call_set_global_hdr_state, daemon=True).start()
                    break

    def process_monitor(self):
        while True:
            if not self.found_process:
                threading.Thread(target=lambda: self.process_thread(), daemon=True).start()
            else:
                if self.toggle_state and not self.is_process_running(self.main_process):
                    self.toggle_state = False
                    self.found_process = False
                    threading.Thread(
                        target=self.call_set_global_hdr_state, daemon=True).start()
            time.sleep(5)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.boot_status = None
        self.toggle_state = False
        self.script_path = f"{os.path.abspath(sys.argv[0])}"
        self.task_name = "PyAutoActions"
        self.config = configparser.ConfigParser()
        self.config.read('processlist.ini')
        self.list_str = self.config['HDR_APPS']['MyList']
        self.process_list = self.list_str.split(', ') if self.list_str else []

        self.warning_message_box = QMessageBox()
        self.warning_message_box.setIcon(QMessageBox.Warning)
        self.warning_message_box.setWindowTitle("Error")
        self.warning_message_box.setFixedSize(400, 200)
        self.settings = QSettings("7gxycn08@Github", "PyAutoActions")
        self.setWindowTitle("PyAutoActions v1.0.0.1")
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
        self.remove_button.clicked.connect(self.remove_selected_entry)
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
        self.run_on_boot_action = QAction('Run on System Boot', self.menu)
        self.run_on_boot_action.setCheckable(True)
        self.run_on_boot_action.setChecked(self.settings.value("start_hidden", False, type=bool))
        self.run_on_boot_action.triggered.connect(self.run_on_boot)
        self.menu.addAction(self.run_on_boot_action)
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
        self.run_initially_at_start()
        monitor = ProcessMonitor(self.process_list,self.toggle_state)
        threading.Thread(target=lambda: monitor.process_monitor(), daemon=True).start()

    def run_on_boot(self):
        try:
            is_checked = self.boot_status

            if is_checked:
                self.remove_task()
                self.run_on_boot_action.setChecked(False)
                self.boot_status = False
            else:
                self.register_as_task()
                self.run_on_boot_action.setChecked(True)
                self.boot_status = True
        except Exception as e:
            tkinter.messagebox.showerror(title="Error", message=f"run_on_boot: {e}")

    def run_initially_at_start(self):
        try:
            if self.is_task_installed() == True:
                self.run_on_boot_action.setChecked(True)
                self.boot_status = True
            else:
                self.run_on_boot_action.setChecked(False)
                self.boot_status = False
        except Exception as e:
            tkinter.messagebox.showerror(title="Error", message=f"run_Initially: {e}")

    def remove_task(self):
        try:
            scheduler = win32com.client.Dispatch('Schedule.Service')
            scheduler.Connect()

            root_folder = scheduler.GetFolder('\\')
            task = root_folder.GetTask(self.task_name)

            root_folder.DeleteTask(self.task_name, 0)

            self.run_on_boot_action.setChecked(False)
            self.boot_status = False

        except Exception as e:
            self.warning_message_box.warning(None, "Error", f"remove_task: {e}", QMessageBox.Ok)

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
            self.warning_message_box.warning(None, "Error", f"is_task_installed: {e}", QMessageBox.Ok)

    def register_as_task(self):
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
            self.run_on_boot_action.setChecked(True)
            self.boot_status = True
        except Exception as e:
            self.warning_message_box.warning(None, "Error", f"register_as_task: {e}", QMessageBox.Ok)

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
        try:
            entry_text = self.entry_line_edit.text()
            if entry_text in self.process_list:
                self.warning_message_box.warning(None, "Error", f"Process {entry_text} already exists in the list.",
                                                 QMessageBox.Ok)
            elif ".exe" not in entry_text:
                self.warning_message_box.warning(None, "Error", f"Manual Entries Require Extensions *.exe",
                                                 QMessageBox.Ok)
            else:
                self.process_list.append(entry_text)
                self.save_config()
                self.update_classes_variables()
                if entry_text:
                    self.list_widget.insertItem(0, entry_text)
                    self.entry_line_edit.clear()
        except Exception as e:
            self.warning_message_box.warning(None, "Error", f"add_entry: {e}", QMessageBox.Ok)

    def remove_selected_entry(self):
        try:
            selected_item = self.list_widget.currentItem()

            if selected_item is not None and selected_item.text().strip():
                selected_text = selected_item.text()
                index_to_remove = self.process_list.index(selected_text)
                self.process_list.pop(index_to_remove)
                self.save_config()
                self.list_widget.takeItem(self.list_widget.row(selected_item))
                self.update_classes_variables()
            else:
                self.warning_message_box.warning(None, "Error", "Nothing to remove.", QMessageBox.Ok)
        except ValueError as ve:
            self.show_error_message(f"Error: {ve}")
        except Exception as e:
            self.warning_message_box.warning(None, "Error", f"Nothing to remove. {e}", QMessageBox.Ok)

    def update_classes_variables(self):
        process_monitor = ProcessMonitor(self.process_list, self.toggle_state)
        process_monitor.toggle_state = self.toggle_state
        process_monitor.process_list = self.process_list

    def add_exe(self):
        try:
            file_dialog = QFileDialog()
            file_path, _ = file_dialog.getOpenFileName(self, "Select Executable", "", "Executable Files (*.exe)")
            if file_path:
                exe_name = os.path.basename(file_path)
                if exe_name in self.process_list:

                    self.warning_message_box.warning(None, "Error", f"Process {exe_name} already exists in the list.",
                                                     QMessageBox.Ok)
                else:
                    self.list_widget.insertItem(0, exe_name)
                    self.process_list.append(exe_name)
                    threading.Thread(target=self.save_config, daemon=True).start()
                    self.update_classes_variables()
        except Exception as e:
            self.warning_message_box.warning(None, "Error", f"add_exe: {e}", QMessageBox.Ok)

    def save_config(self):
        try:
            self.list_str = ', '.join(self.process_list)
            self.config['HDR_APPS'] = {'MyList': self.list_str}

            with open('processlist.ini', 'w') as configfile:
                self.config.write(configfile)
                process_monitor = ProcessMonitor(self.process_list,self.toggle_state)
                process_monitor.toggle_state = self.toggle_state
                process_monitor.process_list = self.process_list
        except Exception as e:
            self.warning_message_box.warning(None, "Error", f"save_config: {e}", QMessageBox.Ok)

    def load_processes_from_config(self):
        try:
            self.list_widget.clear()
            self.config.read('processlist.ini')
            self.update_classes_variables()
            if 'HDR_APPS' in self.config and 'MyList' in self.config['HDR_APPS']:
                process_list_str = self.config['HDR_APPS']['MyList']
                processes = process_list_str.split(', ')
                for process in processes:
                    self.list_widget.insertItem(0, process)
        except Exception as e:
            self.warning_message_box.warning(None, "Error", f"load_processess_from_config: {e}", QMessageBox.Ok)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    sys.exit(app.exec_())

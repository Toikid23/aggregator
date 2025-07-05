# launcher.py

import sys, os, subprocess, webbrowser, time
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit, QLabel, QGroupBox, QGridLayout, QLineEdit)
from PyQt6.QtCore import QThread, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QTextCursor

# --- Imports ---
try: from scraper import run_all_scrapers
except ImportError: run_all_scrapers = None
try: from run_ai_analysis import run_automatic_analysis, run_indeed_analysis
except ImportError: run_automatic_analysis, run_indeed_analysis = None, None
try: from reset_analysis import reset_all_analyses
except ImportError: reset_all_analyses = None

# --- Worker ---
class Stream(QObject):
    new_text = pyqtSignal(str)
    def write(self, text): self.new_text.emit(str(text))
    def flush(self): pass

class Worker(QThread):
    task_finished = pyqtSignal(object)
    def __init__(self, target_function, *args, **kwargs):
        super().__init__(); self.target_function = target_function; self.args = args; self.kwargs = kwargs; self.is_running = True
    def run(self):
        if not hasattr(QApplication.instance(), 'main_window'): self.task_finished.emit(None); return
        stream = Stream(); stream.new_text.connect(QApplication.instance().main_window.append_log)
        sys.stdout = stream; sys.stderr = stream; result = None
        try:
            if self.target_function: result = self.target_function(qthread=self, *self.args, **self.kwargs)
        except Exception as e: print(f"ERREUR CRITIQUE: {e}")
        finally: sys.stdout = sys.__stdout__; sys.stderr = sys.__stderr__; self.task_finished.emit(result)
    def stop(self): self.is_running = False

# --- FENÊTRE PRINCIPALE ---
class AppLauncher(QWidget):
    def __init__(self):
        super().__init__(); self.worker = None; self.flask_process = None
        QApplication.instance().main_window = self; self.initUI()
    def initUI(self):
        self.setWindowTitle('Tableau de Bord - Job Aggregator'); self.setGeometry(100, 100, 900, 700)
        main_layout, left_layout, self.right_layout = QHBoxLayout(), QVBoxLayout(), QVBoxLayout()
        title_label = QLabel('Tableau de Bord'); title_label.setFont(QFont('Arial', 18, QFont.Weight.Bold)); left_layout.addWidget(title_label)
        scraping_group = QGroupBox("Workflow Principal"); scraping_layout = QVBoxLayout()
        self.btn_scrape = QPushButton('1. Lancer le Scraping'); self.btn_scrape.clicked.connect(lambda: self.run_task(run_all_scrapers, show_summary=True))
        scraping_layout.addWidget(self.btn_scrape)
        self.btn_stop_scrape = QPushButton("Arrêter le Scraping"); self.btn_stop_scrape.clicked.connect(self.stop_current_task); self.btn_stop_scrape.setEnabled(False); self.btn_stop_scrape.setStyleSheet("background-color: #ffc107;")
        scraping_layout.addWidget(self.btn_stop_scrape)
        scraping_group.setLayout(scraping_layout); left_layout.addWidget(scraping_group)
        ai_group = QGroupBox("Analyse IA"); ai_layout = QGridLayout()
        self.btn_analyze_auto = QPushButton("Analyser Tout (sauf Indeed)"); self.btn_analyze_auto.clicked.connect(lambda: self.run_task(run_automatic_analysis))
        ai_layout.addWidget(self.btn_analyze_auto, 0, 0)
        self.btn_analyze_indeed = QPushButton("Analyser Indeed"); self.btn_analyze_indeed.clicked.connect(lambda: self.run_task(run_indeed_analysis))
        ai_layout.addWidget(self.btn_analyze_indeed, 0, 1)
        self.btn_stop_ai = QPushButton("Arrêter l'Analyse"); self.btn_stop_ai.clicked.connect(self.stop_current_task); self.btn_stop_ai.setEnabled(False); self.btn_stop_ai.setStyleSheet("background-color: #ffc107;")
        ai_layout.addWidget(self.btn_stop_ai, 1, 0, 1, 2)
        ai_group.setLayout(ai_layout); left_layout.addWidget(ai_group)
        webapp_group = QGroupBox("Application Web"); webapp_layout = QVBoxLayout()
        start_stop_layout = QHBoxLayout()
        self.btn_start_server = QPushButton("Démarrer Serveur Web"); self.btn_start_server.clicked.connect(self.start_web_app); self.btn_start_server.setStyleSheet("background-color: #28a745; color: white;")
        start_stop_layout.addWidget(self.btn_start_server)
        self.btn_stop_server = QPushButton("Arrêter Serveur Web"); self.btn_stop_server.clicked.connect(self.stop_web_app); self.btn_stop_server.setStyleSheet("background-color: #dc3545; color: white;"); self.btn_stop_server.setEnabled(False)
        start_stop_layout.addWidget(self.btn_stop_server)
        webapp_layout.addLayout(start_stop_layout)
        link_layout = QHBoxLayout(); self.link_display = QLineEdit("Serveur arrêté."); self.link_display.setReadOnly(True); link_layout.addWidget(self.link_display)
        self.btn_copy_link = QPushButton("Copier"); self.btn_copy_link.clicked.connect(self.copy_link); self.btn_copy_link.setEnabled(False); link_layout.addWidget(self.btn_copy_link)
        webapp_group.setLayout(webapp_layout); left_layout.addWidget(webapp_group)
        maintenance_group = QGroupBox("Maintenance"); maintenance_layout = QGridLayout()
        self.btn_reset = QPushButton("Réinitialiser Analyses"); self.btn_reset.clicked.connect(lambda: self.run_task(reset_all_analyses)); maintenance_layout.addWidget(self.btn_reset, 0, 0)
        self.btn_delete_db = QPushButton("Supprimer DB"); self.btn_delete_db.clicked.connect(self.delete_database); maintenance_layout.addWidget(self.btn_delete_db, 0, 1)
        self.btn_create_indeed = QPushButton("Session Indeed"); self.btn_create_indeed.clicked.connect(lambda: self.run_script_file('create_session.py')); maintenance_layout.addWidget(self.btn_create_indeed, 1, 0)
        self.btn_create_glassdoor = QPushButton("Session Glassdoor"); self.btn_create_glassdoor.clicked.connect(lambda: self.run_script_file('create_session_glassdoor.py')); maintenance_layout.addWidget(self.btn_create_glassdoor, 1, 1)
        maintenance_group.setLayout(maintenance_layout); left_layout.addWidget(maintenance_group)
        left_layout.addStretch()
        self.summary_group = QGroupBox("Résumé du Dernier Scraping"); summary_inner_layout = QVBoxLayout(); summary_inner_layout.addWidget(QLabel("Lancez un scraping...")); summary_inner_layout.addStretch()
        self.summary_group.setLayout(summary_inner_layout); self.summary_group.setFixedHeight(250); self.right_layout.addWidget(self.summary_group)
        self.right_layout.addWidget(QLabel("Logs en direct :")); self.log_console = QTextEdit(); self.log_console.setReadOnly(True); self.log_console.setFont(QFont('Courier', 10)); self.log_console.setStyleSheet("background-color: #2b2b2b; color: #f0f0f0;")
        self.right_layout.addWidget(self.log_console)
        main_layout.addLayout(left_layout, 1); main_layout.addLayout(self.right_layout, 2); self.setLayout(main_layout)

    def run_task(self, target_function, show_summary=False):
        if not target_function: self.append_log("ERREUR: Tâche non disponible."); return
        self.log_console.clear()
        if show_summary: self.clear_summary()
        self.append_log(f"--- Démarrage : {target_function.__name__} ---\n")
        is_stoppable_task = target_function in [run_all_scrapers, run_automatic_analysis, run_indeed_analysis]
        self.disable_buttons(is_stoppable_task)
        self.worker = Worker(target_function)
        self.worker.task_finished.connect(lambda result: self.on_task_finished(result, show_summary))
        self.worker.start()
        
    def stop_current_task(self):
        if self.worker and self.worker.isRunning():
            self.append_log("\n--- [!] Tentative d'arrêt de la tâche en cours... ---")
            self.worker.stop()
            self.btn_stop_ai.setEnabled(False)
            self.btn_stop_scrape.setEnabled(False)

    def on_task_finished(self, result, show_summary):
        self.append_log("\n--- Tâche terminée ! ---")
        self.enable_buttons()
        if show_summary:
            self.update_summary(result)

    # --- AMÉLIORATION DE LA LOGIQUE D'ARRÊT DES BOUTONS ---
    def disable_buttons(self, is_stoppable_task=False):
        # Désactive tous les boutons
        for btn in self.findChildren(QPushButton):
            btn.setEnabled(False)
        # Puis réactive spécifiquement le bouton d'arrêt pour la bonne tâche
        if is_stoppable_task:
            if self.worker and self.worker.target_function == run_all_scrapers:
                self.btn_stop_scrape.setEnabled(True)
            elif self.worker and self.worker.target_function in [run_automatic_analysis, run_indeed_analysis]:
                self.btn_stop_ai.setEnabled(True)
    
    def enable_buttons(self):
        # Réactive tous les boutons normaux
        for btn in [self.btn_scrape, self.btn_analyze_auto, self.btn_analyze_indeed, self.btn_reset, self.btn_create_indeed, self.btn_create_glassdoor, self.btn_delete_db]:
             if btn: btn.setEnabled(True)
        # Gère l'état des boutons serveur
        is_server_running = bool(self.flask_process and self.flask_process.poll() is None)
        self.btn_start_server.setEnabled(not is_server_running)
        self.btn_stop_server.setEnabled(is_server_running)
        # S'assure que les boutons d'arrêt sont bien désactivés
        self.btn_stop_scrape.setEnabled(False)
        self.btn_stop_ai.setEnabled(False)

    # --- NOUVELLE FONCTION `closeEvent` AMÉLIORÉE ---
    def closeEvent(self, event):
        """Cette fonction est appelée automatiquement quand on ferme la fenêtre."""
        self.append_log("\n--- Fermeture de l'application... ---")
        
        # 1. Arrêter le serveur Flask s'il tourne
        if self.flask_process and self.flask_process.poll() is None:
            self.stop_web_app()
        
        # 2. Arrêter le worker s'il tourne
        if self.worker and self.worker.isRunning():
            self.append_log("-> Arrêt de la tâche en arrière-plan...")
            self.worker.stop()
            # On attend un peu que le thread se termine proprement
            if not self.worker.wait(2000): # Attendre 2 secondes max
                self.append_log("-> Le thread ne s'est pas arrêté, on le force.")
                self.worker.terminate() # Méthode plus brutale si nécessaire
                self.worker.wait()

        self.append_log("--- Application fermée. ---")
        event.accept() # Accepte l'événement de fermeture


    def start_web_app(self):
        if self.flask_process and self.flask_process.poll() is None: self.append_log("\n[INFO] Le serveur Flask est déjà en cours d'exécution."); return
        self.append_log("\n--- Démarrage du serveur Flask (app.py)... ---")
        try: self.flask_process = subprocess.Popen([sys.executable, 'app.py']); self.append_log(f"[SUCCÈS] Serveur démarré avec le PID: {self.flask_process.pid}"); self.btn_start_server.setEnabled(False); self.btn_stop_server.setEnabled(True); self.link_display.setText("http://127.0.0.1:5000"); self.btn_copy_link.setEnabled(True)
        except Exception as e: self.append_log(f"[ERREUR] Impossible de lancer le serveur Flask: {e}")

    def stop_web_app(self):
        if self.flask_process and self.flask_process.poll() is None: self.append_log("\n--- Arrêt du serveur Flask... ---"); self.flask_process.terminate(); self.flask_process.wait(); self.append_log(f"[SUCCÈS] Serveur avec PID {self.flask_process.pid} arrêté."); self.flask_process = None
        else: self.append_log("\n[INFO] Le serveur n'était pas en cours d'exécution.")
        self.btn_start_server.setEnabled(True); self.btn_stop_server.setEnabled(False); self.link_display.setText("Serveur arrêté."); self.btn_copy_link.setEnabled(False)

    def copy_link(self): QApplication.clipboard().setText(self.link_display.text()); self.append_log("\n[INFO] Lien copié dans le presse-papiers.")

    def clear_summary(self):
        layout = self.summary_group.layout()
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        default_label = QLabel("Résumé en cours de génération...")
        layout.addWidget(default_label)
        layout.addStretch()

    def update_summary(self, summary_data):
        layout = self.summary_group.layout()
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        if not summary_data:
            layout.addWidget(QLabel("Aucun résumé à afficher."))
            layout.addStretch()
            return
        for site, message in summary_data.items():
            label = QLabel(f"<b>{site}:</b> {message}")
            label.setStyleSheet("color: red;" if "ÉCHEC" in message else "color: green;")
            layout.addWidget(label)
        layout.addStretch()

    def delete_database(self):
        db_file = 'jobs.db'; self.append_log(f"\n--- Tentative de suppression de '{db_file}' ---")
        if os.path.exists(db_file):
            try: os.remove(db_file); self.append_log(f"[SUCCÈS] Le fichier '{db_file}' a été supprimé.")
            except Exception as e: self.append_log(f"[ERREUR] Impossible de supprimer le fichier : {e}")
        else: self.append_log(f"[INFO] Le fichier '{db_file}' n'existe pas.")

    def run_script_file(self, filename):
        self.append_log(f"\n--- Tentative de lancement de '{filename}'... ---")
        try: subprocess.Popen(['gnome-terminal', '--', sys.executable, filename])
        except FileNotFoundError:
            try: subprocess.Popen(['cmd', '/c', 'start', 'python', filename])
            except Exception as e: self.append_log(f"ERREUR: {e}")

    def append_log(self, message):
        self.log_console.moveCursor(QTextCursor.MoveOperation.End); self.log_console.insertPlainText(str(message).strip() + '\n')

    def disable_buttons(self, is_stoppable_task=False):
        for btn in self.findChildren(QPushButton):
            if btn in [self.btn_stop_scrape, self.btn_stop_ai] and is_stoppable_task:
                # Gère l'activation du bon bouton stop
                if self.worker and self.worker.target_function == run_all_scrapers:
                    self.btn_stop_scrape.setEnabled(True)
                else:
                    self.btn_stop_ai.setEnabled(True)
            else:
                btn.setEnabled(False)
        
    def enable_buttons(self):
        for btn in [self.btn_scrape, self.btn_analyze_auto, self.btn_analyze_indeed, self.btn_reset, self.btn_create_indeed, self.btn_create_glassdoor, self.btn_delete_db]:
             if btn: btn.setEnabled(True)
        is_server_running = bool(self.flask_process and self.flask_process.poll() is None)
        self.btn_start_server.setEnabled(not is_server_running)
        self.btn_stop_server.setEnabled(is_server_running)
        self.btn_stop_scrape.setEnabled(False)
        self.btn_stop_ai.setEnabled(False)

    def closeEvent(self, event): self.stop_web_app(); event.accept()

# --- Point d'entrée ---
if __name__ == '__main__':
    app_gui = QApplication(sys.argv); launcher = AppLauncher(); launcher.show(); sys.exit(app_gui.exec())
import configparser
import os
import threading
import time
import tkinter as tk
from tkinter import messagebox, simpledialog

import pystray
from PIL import Image
from pystray import Menu, MenuItem as item

from app.paths import config_file
from core.analyzer import get_default_model
from core.ollama_manager import get_installed_models
from ui.window_icon import apply_window_icon
from utils.logger import logger

MODEL_CACHE_TTL_SECONDS = 60
TRAY_MENU_CLOSE_DELAY_MS = 450


class TrayApp:
    def __init__(
        self,
        run_analysis_callback,
        get_icon_path_callback,
        auto_interval_callback,
        get_auto_interval_callback,
        open_dashboard_callback=None,
        shutdown_callback=None,
    ):
        self.run_analysis_callback = run_analysis_callback
        self.get_icon_path_callback = get_icon_path_callback
        self.auto_interval_callback = auto_interval_callback
        self.get_auto_interval_callback = get_auto_interval_callback
        self.open_dashboard_callback = open_dashboard_callback
        self.shutdown_callback = shutdown_callback
        self.icon = None
        self._models_cache = []
        self._models_cache_at = 0.0
        self._models_refreshing = False
        self.hidden_root = tk.Tk()
        self.hidden_root.withdraw()
        apply_window_icon(self.hidden_root)

    def _run_on_tk(self, callback, *args, delay_ms=0):
        try:
            self.hidden_root.after(delay_ms, lambda: callback(*args))
        except Exception as e:
            logger.error(f"Erro ao agendar acao no Tk: {e}")

    def _get_installed_models_cached(self):
        if time.time() - self._models_cache_at > MODEL_CACHE_TTL_SECONDS:
            self._refresh_models_async()
        return list(self._models_cache)

    def _refresh_models_async(self):
        if self._models_refreshing:
            return
        self._models_refreshing = True

        def worker():
            try:
                self._models_cache = get_installed_models()
                self._models_cache_at = time.time()
                if self.icon:
                    self.icon.menu = self.build_menu()
            except Exception as e:
                logger.error(f"Erro ao listar modelos do Ollama: {e}")
            finally:
                self._models_refreshing = False

        threading.Thread(target=worker, daemon=True).start()

    def build_menu(self):
        installed = self._get_installed_models_cached()

        supported_local_models = ["gemma3:4b", "llama3.2:3b", "qwen2.5:3b", "phi4-mini:latest"]
        visible_local_models = [model for model in supported_local_models if model in installed]
        all_models = ["gpt-4o-mini"] + visible_local_models
        if not installed:
            all_models += supported_local_models

        def set_model(model_name):
            def action(icon, menu_item):
                try:
                    config = configparser.ConfigParser()
                    config_path = config_file()
                    config.read(config_path)
                    if "Models" not in config:
                        config.add_section("Models")
                    config["Models"]["default_model"] = model_name
                    with open(config_path, "w", encoding="utf-8") as f:
                        config.write(f)
                    if self.icon:
                        self.icon.menu = self.build_menu()
                    logger.info(f"Modelo padrao alterado para {model_name}.")
                except Exception as e:
                    logger.error(f"Erro ao alterar modelo padrao: {e}")

            return action

        def is_checked(model_name):
            return lambda menu_item: get_default_model() == model_name

        model_items = [
            item(model, set_model(model), checked=is_checked(model), radio=True)
            for model in all_models
        ]

        def set_auto_interval(interval):
            def action(icon, menu_item):
                def apply_interval():
                    self.auto_interval_callback(interval)
                    if self.icon:
                        self.icon.menu = self.build_menu()

                try:
                    self._run_on_tk(apply_interval)
                except Exception as e:
                    logger.error(f"Erro ao alterar monitoramento automatico: {e}")

            return action

        def is_auto_checked(interval):
            return lambda menu_item: self.get_auto_interval_callback() == interval

        def parse_custom_interval(value):
            raw = (value or "").strip().lower().replace(",", ".")
            if not raw:
                return None

            digits = "".join(ch for ch in raw if ch.isdigit() or ch == ".")
            if not digits:
                return None

            try:
                amount = float(digits)
            except ValueError:
                return None

            if amount <= 0:
                return None

            is_minutes = any(token in raw for token in ["m", "min", "minuto"])
            seconds = int(amount * 60) if is_minutes else int(amount)
            return max(5, seconds)

        def open_custom_interval(icon, menu_item):
            self.hidden_root.after(0, self._ask_custom_interval, parse_custom_interval)

        current_interval = self.get_auto_interval_callback()
        preset_intervals = {0, 180, 300, 600}
        custom_label = "Personalizado..."
        if current_interval not in preset_intervals and current_interval > 0:
            custom_label = f"Personalizado: {self._format_interval(current_interval)}"

        auto_items = [
            item("Desativado", set_auto_interval(0), checked=is_auto_checked(0), radio=True),
            item("A cada 3 minutos", set_auto_interval(180), checked=is_auto_checked(180), radio=True),
            item("A cada 5 minutos", set_auto_interval(300), checked=is_auto_checked(300), radio=True),
            item("A cada 10 minutos", set_auto_interval(600), checked=is_auto_checked(600), radio=True),
            item(
                custom_label,
                open_custom_interval,
                checked=lambda menu_item: self.get_auto_interval_callback() not in preset_intervals
                and self.get_auto_interval_callback() > 0,
                radio=True,
            ),
        ]

        current_model = get_default_model()
        monitor_label = "desativado"
        if current_interval > 0:
            monitor_label = self._format_interval(current_interval)

        return Menu(
            item("CyberDetect ativo", self._noop, enabled=False),
            item(f"Modelo atual: {current_model}", self._noop, enabled=False),
            item(f"Monitoramento: {monitor_label}", self._noop, enabled=False),
            Menu.SEPARATOR,
            item("Abrir painel principal", self.on_dashboard_clicked),
            item("Analisar tela agora", self.on_analyze_clicked, default=True),
            Menu.SEPARATOR,
            item("Monitoramento automatico", Menu(*auto_items)),
            item("Modelo de IA", Menu(*model_items)),
            Menu.SEPARATOR,
            item("Sair do CyberDetect", self.on_exit_clicked),
        )

    def run(self):
        image_path = self.get_icon_path_callback("safe")
        if not os.path.exists(image_path):
            image = Image.new("RGBA", (64, 64), color=(12, 2, 20, 255))
        else:
            image = Image.open(image_path).convert("RGBA")

        self.icon = pystray.Icon("CyberDetect", image, "CyberDetect - Protecao contra golpes", self.build_menu())
        threading.Thread(target=self.icon.run, daemon=True).start()
        self.hidden_root.mainloop()

    def _noop(self, icon=None, menu_item=None):
        return None

    def _format_interval(self, interval_seconds):
        if interval_seconds % 60 == 0:
            minutes = interval_seconds // 60
            unit = "minuto" if minutes == 1 else "minutos"
            return f"{minutes} {unit}"
        unit = "segundo" if interval_seconds == 1 else "segundos"
        return f"{interval_seconds} {unit}"

    def _ask_custom_interval(self, parser):
        try:
            value = simpledialog.askstring(
                "Intervalo personalizado",
                "Digite o intervalo. Exemplos: 15s, 30 segundos, 2m, 5 minutos.",
                parent=self.hidden_root,
            )
            if value is None:
                return

            interval = parser(value)
            if interval is None:
                messagebox.showerror(
                    "Intervalo invalido",
                    "Digite um intervalo valido, como 15s, 30 segundos ou 2m.",
                    parent=self.hidden_root,
                )
                return

            self.auto_interval_callback(interval)
            if self.icon:
                self.icon.menu = self.build_menu()
        except Exception as e:
            logger.error(f"Erro ao configurar intervalo personalizado: {e}")

    def update_icon(self, state: str):
        try:
            if self.icon:
                path = self.get_icon_path_callback(state)
                if os.path.exists(path):
                    self.icon.icon = Image.open(path).convert("RGBA")
        except Exception as e:
            logger.error(f"Erro ao atualizar icone do tray: {e}")

    def on_analyze_clicked(self, icon, menu_item):
        logger.info("Solicitada analise manual via Tray.")
        self._run_on_tk(self.run_analysis_callback, delay_ms=TRAY_MENU_CLOSE_DELAY_MS)

    def on_dashboard_clicked(self, icon, menu_item):
        logger.info("Abrindo painel principal.")
        if self.open_dashboard_callback:
            self.hidden_root.after(0, self.open_dashboard_callback)

    def on_exit_clicked(self, icon, menu_item):
        logger.info("Encerrando CyberDetect.")
        def shutdown():
            if self.shutdown_callback:
                try:
                    self.shutdown_callback()
                except Exception as e:
                    logger.error(f"Erro na limpeza antes de encerrar: {e}")
            if self.icon:
                self.icon.stop()
            try:
                self.hidden_root.quit()
                self.hidden_root.destroy()
            except Exception:
                pass
            os._exit(0)

        self._run_on_tk(shutdown)

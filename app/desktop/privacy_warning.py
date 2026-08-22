import customtkinter as ctk

from ui.window_icon import apply_window_icon

class PrivacyWarningWindow(ctk.CTkToplevel):
    def __init__(self, parent, on_accept, on_cancel=None):
        super().__init__(parent)
        self.title("Aviso de Privacidade - CyberDetect")
        self.geometry("500x350")
        self.resizable(False, False)
        apply_window_icon(self)
        self.attributes("-topmost", True)
        
        self.on_accept_callback = on_accept
        self.on_cancel_callback = on_cancel
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Centraliza a janela
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 500) // 2
        y = (self.winfo_screenheight() - 350) // 2
        self.geometry(f"+{x}+{y}")

        self.setup_ui()
        self.grab_set() # Torna a janela modal

    def setup_ui(self):
        title_lbl = ctk.CTkLabel(self, text="⚠️ ATENÇÃO DE PRIVACIDADE", font=ctk.CTkFont(size=20, weight="bold"), text_color="#FF5555")
        title_lbl.pack(pady=(20, 10))

        warning_text = (
            "O modelo GPT-4o Mini processa os dados em servidores\n"
            "da OpenAI (EUA). O texto da conversa capturada será\n"
            "enviado externamente para análise.\n\n"
            "Não utilize este modo com conversas que contenham\n"
            "senhas, documentos ou dados bancários.\n\n"
            "Para privacidade total, utilize um modelo local via Ollama."
        )
        
        msg_lbl = ctk.CTkLabel(self, text=warning_text, font=ctk.CTkFont(size=14), justify="center")
        msg_lbl.pack(pady=10)

        self.check_var = ctk.BooleanVar(value=False)
        self.checkbox = ctk.CTkCheckBox(self, text="Entendi e desejo continuar usando a API externa", variable=self.check_var, command=self.on_check)
        self.checkbox.pack(pady=20)

        self.btn_continue = ctk.CTkButton(self, text="Continuar", state="disabled", command=self.on_continue)
        self.btn_continue.pack(pady=10)

    def on_check(self):
        if self.check_var.get():
            self.btn_continue.configure(state="normal")
        else:
            self.btn_continue.configure(state="disabled")

    def on_continue(self):
        self.destroy()
        if self.on_accept_callback:
            self.on_accept_callback()

    def on_close(self):
        self.destroy()
        if self.on_cancel_callback:
            self.on_cancel_callback()

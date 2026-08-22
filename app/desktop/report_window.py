import customtkinter as ctk

from ui.window_icon import apply_window_icon

class ReportWindow(ctk.CTkToplevel):
    def __init__(self, parent=None, result_data=None):
        super().__init__(parent)
        self.title("Relatório de Análise - CyberDetect")
        self.geometry("600x700")
        apply_window_icon(self)
        self.result_data = result_data or {}
        
        # Centraliza
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 600) // 2
        y = (self.winfo_screenheight() - 700) // 2
        self.geometry(f"+{x}+{y}")

        self.setup_ui()

    def setup_ui(self):
        # Cabeçalho
        frame_header = ctk.CTkFrame(self)
        frame_header.pack(fill="x", padx=10, pady=10)
        
        classif = self.result_data.get("classificacao", "ERRO")
        try:
            score = int(self.result_data.get("score_risco", 0) or 0)
        except (TypeError, ValueError):
            score = 0
        score = max(0, min(100, score))
        
        color = "green" if classif == "SEGURO" else "orange" if classif == "SUSPEITO" else "red"
        if classif == "ERRO": color = "gray"
        
        ctk.CTkLabel(frame_header, text=f"Classificação: {classif}", text_color=color, font=ctk.CTkFont(size=24, weight="bold")).pack(pady=5)
        
        if classif != "ERRO":
            progress = ctk.CTkProgressBar(frame_header, progress_color=color)
            progress.pack(pady=5, padx=20, fill="x")
            progress.set(score / 100.0)
            
            ctk.CTkLabel(frame_header, text=f"Score de Risco: {score}/100", font=ctk.CTkFont(size=14)).pack()
            
        tipo_golpe = self.result_data.get("tipo_golpe")
        if tipo_golpe:
            ctk.CTkLabel(frame_header, text=f"Tipo Identificado: {tipo_golpe}", font=ctk.CTkFont(weight="bold")).pack(pady=5)
            
        # Conteúdo em scroll
        scroll = ctk.CTkScrollableFrame(self)
        scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        resumo = self.result_data.get("resumo", "Sem resumo disponível.")
        ctk.CTkLabel(scroll, text="Resumo da Análise:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(10,0))
        ctk.CTkLabel(scroll, text=resumo, justify="left", wraplength=500).pack(anchor="w", pady=(0, 10))
        
        recomendacao = self.result_data.get("recomendacao", "")
        if recomendacao:
            ctk.CTkLabel(scroll, text="Recomendação:", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
            ctk.CTkLabel(scroll, text=recomendacao, justify="left", wraplength=500, text_color="cyan").pack(anchor="w", pady=(0, 10))
            
        fatores = self.result_data.get("fatores_risco", [])
        if not isinstance(fatores, list):
            fatores = []
        if fatores:
            ctk.CTkLabel(scroll, text="Composicao do Risco:", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
            for fator in fatores:
                if not isinstance(fator, dict):
                    continue
                nome = fator.get("fator") or fator.get("factor") or "Fator de risco"
                peso = fator.get("peso") if fator.get("peso") is not None else fator.get("weight", 0)
                categoria = fator.get("categoria") or fator.get("category") or "geral"
                evidencia = fator.get("evidencia") or fator.get("evidence") or "Evidencia normalizada pelo backend."
                txt = f"+{peso}% [{categoria}] {nome}\n  Evidencia: {evidencia}"
                ctk.CTkLabel(scroll, text=txt, justify="left", wraplength=500).pack(anchor="w", pady=5)

        pontos = self.result_data.get("pontos_suspeitos", [])
        if not isinstance(pontos, list):
            pontos = []
        if pontos:
            ctk.CTkLabel(scroll, text="Pontos Suspeitos:", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
            for p in pontos:
                if not isinstance(p, dict):
                    continue
                trecho = p.get("trecho", "")
                motivo = p.get("motivo", "")
                grav = p.get("gravidade", "")
                txt = f"• [{grav}] \"{trecho}\"\n  Motivo: {motivo}"
                ctk.CTkLabel(scroll, text=txt, justify="left", wraplength=500).pack(anchor="w", pady=5)
                
        tecnicas = self.result_data.get("tecnicas_engenharia_social", [])
        if not isinstance(tecnicas, list):
            tecnicas = []
        if tecnicas:
            ctk.CTkLabel(scroll, text="Técnicas de Engenharia Social:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(10,0))
            for t in tecnicas:
                ctk.CTkLabel(scroll, text=f"- {t}", justify="left").pack(anchor="w")
                
        # Botão Fechar
        ctk.CTkButton(self, text="Fechar", command=self.destroy).pack(pady=10)

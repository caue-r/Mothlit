"""Janela principal do Mothlit: estreita, sem borda do Windows, com barra de título própria."""

import ctypes
import sys
import time

import customtkinter as ctk

from .. import config
from ..config import ErroConfiguracao
from ..devices import criar_ar, criar_lampada
from . import tema
from .painel_ar import PainelAr
from .painel_lampada import PainelLampada
from .widgets import Abas, BotaoIcone
from .worker import Worker

LARGURA, ALTURA = 440, 740


class App(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=tema.FUNDO)
        self.title("Mothlit")
        self.geometry(f"{LARGURA}x{ALTURA}")
        self.resizable(False, False)
        self.worker = Worker(self)
        self._erro_visivel_ate = 0.0

        self._barra_titulo()

        self.abas = Abas(self, ["Clima", "Luz"], self._trocar_aba, altura=42)
        self.abas.pack(fill="x", padx=20, pady=(4, 14))

        self.conteudo = ctk.CTkFrame(self, fg_color="transparent")
        self.conteudo.pack(fill="both", expand=True, padx=20)
        self.painel_ar = PainelAr(self.conteudo, self.worker, self.mostrar_status)
        self.painel_lampada = PainelLampada(self.conteudo, self.worker, self.mostrar_status)

        rodape = ctk.CTkFrame(self, fg_color="transparent")
        rodape.pack(fill="x", padx=20, pady=(8, 16))
        self.barra = ctk.CTkLabel(rodape, text="", font=tema.fonte(11), text_color=tema.TEXTO_SUAVE, anchor="w")
        self.barra.pack(side="left", fill="x", expand=True)
        BotaoIcone(rodape, tema.ICONE_ATUALIZAR, self.atualizar, tamanho=38, tamanho_icone=15).pack(side="right")

        self._trocar_aba("Clima")
        self._conectar(self.painel_lampada, criar_lampada)
        self._conectar(self.painel_ar, criar_ar)
        self.protocol("WM_DELETE_WINDOW", self.fechar)
        self.after(10, self._janela_sem_borda)
        self.atualizar()

    # --- barra de título própria ---

    def _barra_titulo(self) -> None:
        barra = ctk.CTkFrame(self, fg_color="transparent", height=56)
        barra.pack(fill="x", padx=20, pady=(14, 8))
        logo = ctk.CTkLabel(barra, text="", width=34, height=34, corner_radius=10, fg_color="#2f7fe0",
                            image=tema.icone(tema.ICONE_CASA, 16, "#ffffff"))
        logo.pack(side="left")
        titulo = ctk.CTkLabel(barra, text="Mothlit", font=tema.fonte(17), text_color=tema.TEXTO)
        titulo.pack(side="left", padx=12)
        BotaoIcone(barra, tema.ICONE_FECHAR, self.fechar, tamanho=34, tamanho_icone=12).pack(side="right")
        BotaoIcone(barra, tema.ICONE_MINIMIZAR, self.minimizar, tamanho=34, tamanho_icone=12).pack(
            side="right", padx=8)
        BotaoIcone(barra, tema.ICONE_ENGRENAGEM, self.abrir_configuracoes, tamanho=34, tamanho_icone=14).pack(
            side="right")
        # arrastar a janela pela barra
        for w in (barra, titulo, logo):
            w.bind("<ButtonPress-1>", self._iniciar_arraste)
            w.bind("<B1-Motion>", self._arrastar)

    def _iniciar_arraste(self, e) -> None:
        self._arraste = (e.x_root - self.winfo_x(), e.y_root - self.winfo_y())

    def _arrastar(self, e) -> None:
        dx, dy = self._arraste
        self.geometry(f"+{e.x_root - dx}+{e.y_root - dy}")

    def _janela_sem_borda(self) -> None:
        """Remove a moldura do Windows mantendo ícone na barra de tarefas e cantos arredondados (Win 11)."""
        self.overrideredirect(True)
        if sys.platform != "win32":
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            GWL_EXSTYLE, WS_EX_APPWINDOW, WS_EX_TOOLWINDOW = -20, 0x00040000, 0x00000080
            estilo = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, (estilo & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW)
            DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND = 33, 2
            preferencia = ctypes.c_int(DWMWCP_ROUND)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
                                                       ctypes.byref(preferencia), ctypes.sizeof(preferencia))
            self._hwnd = hwnd
        except (AttributeError, OSError):
            self._hwnd = None
        # reaplica o estilo para a barra de tarefas reconhecer a janela
        self.withdraw()
        self.after(10, self.deiconify)

    def minimizar(self) -> None:
        hwnd = getattr(self, "_hwnd", None)
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE (iconify() não funciona sem moldura)
        else:
            self.iconify()

    # --- conteúdo ---

    def _trocar_aba(self, nome: str) -> None:
        self.painel_ar.pack_forget()
        self.painel_lampada.pack_forget()
        (self.painel_ar if nome == "Clima" else self.painel_lampada).pack(fill="both", expand=True)

    @staticmethod
    def _conectar(painel, fabrica) -> None:
        try:
            painel.definir_dispositivo(fabrica())
        except ErroConfiguracao as e:
            painel.definir_dispositivo(None, str(e))

    def atualizar(self) -> None:
        self.mostrar_status("Atualizando…")
        self.painel_lampada.atualizar()
        self.painel_ar.atualizar()

    def mostrar_status(self, mensagem: str, erro: bool = False, sutil: bool = False) -> None:
        """`sutil`: mensagens de rotina, que não devem esconder um erro recente."""
        agora = time.monotonic()
        if sutil and agora < self._erro_visivel_ate:
            return
        self._erro_visivel_ate = agora + 8 if erro else 0.0
        texto = f"{time.strftime('%H:%M')} · {mensagem}" if erro else mensagem
        self.barra.configure(text=texto, text_color=tema.ERRO if erro else tema.TEXTO_SUAVE)

    def abrir_configuracoes(self) -> None:
        janela = ctk.CTkToplevel(self, fg_color=tema.FUNDO)
        janela.title("Configurações")
        janela.geometry("420x230")
        janela.transient(self)
        cfg = config.carregar()
        linhas = [
            ("Lâmpada", f"{cfg.lampada_ip or '–'}  ·  protocolo {cfg.lampada_versao}"),
            ("Ar-condicionado", cfg.ar_device_id or "–"),
            ("Arquivo .env", str(config.caminho_env())),
            ("Segredos", "Gerenciador de Credenciais do Windows (mothlit)"),
        ]
        for rotulo, valor in linhas:
            ctk.CTkLabel(janela, text=rotulo, font=tema.fonte(11), text_color=tema.TEXTO_SUAVE, anchor="w",
                         height=14).pack(fill="x", padx=20, pady=(10, 0))
            ctk.CTkLabel(janela, text=valor, font=tema.fonte(12), text_color=tema.TEXTO, anchor="w",
                         wraplength=380, justify="left").pack(fill="x", padx=20)
        ctk.CTkLabel(janela, text="Para reconfigurar: uv run python -m mothlit setup", font=tema.fonte(11),
                     text_color=tema.DESTAQUE, anchor="w").pack(fill="x", padx=20, pady=(14, 0))

    def fechar(self) -> None:
        self.worker.encerrar()
        self.destroy()


def executar() -> None:
    ctk.set_appearance_mode("dark")
    App().mainloop()

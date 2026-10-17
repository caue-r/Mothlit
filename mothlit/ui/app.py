"""Janela principal do Mothlit."""

import time

import customtkinter as ctk

from ..config import ErroConfiguracao
from ..devices import criar_ar, criar_lampada
from .comum import COR_ERRO
from .painel_ar import PainelAr
from .painel_lampada import PainelLampada
from .worker import Worker


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Mothlit")
        self.geometry("820x520")
        self.minsize(640, 460)

        self.worker = Worker(self)

        # Cabeçalho
        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.pack(fill="x", padx=20, pady=(16, 8))
        ctk.CTkLabel(topo, text="Mothlit", font=ctk.CTkFont(size=24, weight="bold")).pack(side="left")
        ctk.CTkButton(topo, text="⟳ Atualizar", width=110, command=self.atualizar).pack(side="right")

        # Painéis lado a lado
        area = ctk.CTkFrame(self, fg_color="transparent")
        area.pack(fill="both", expand=True, padx=20)
        area.grid_columnconfigure((0, 1), weight=1, uniform="col")
        area.grid_rowconfigure(0, weight=1)
        self.painel_lampada = PainelLampada(area, self.worker, self.mostrar_status)
        self.painel_lampada.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.painel_ar = PainelAr(area, self.worker, self.mostrar_status)
        self.painel_ar.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        # Barra de status
        self.barra = ctk.CTkLabel(self, text="", anchor="w", text_color="gray")
        self.barra.pack(fill="x", padx=22, pady=(8, 10))

        self._conectar(self.painel_lampada, criar_lampada)
        self._conectar(self.painel_ar, criar_ar)
        self.protocol("WM_DELETE_WINDOW", self.fechar)
        self.atualizar()

    @staticmethod
    def _conectar(painel, fabrica) -> None:
        try:
            painel.definir_dispositivo(fabrica())
        except ErroConfiguracao as e:
            painel.definir_dispositivo(None, str(e))

    def atualizar(self) -> None:
        self.painel_lampada.atualizar()
        self.painel_ar.atualizar()

    def mostrar_status(self, mensagem: str, erro: bool = False) -> None:
        hora = time.strftime("%H:%M:%S")
        self.barra.configure(text=f"{hora}  {mensagem}", text_color=COR_ERRO if erro else "gray")

    def fechar(self) -> None:
        self.worker.encerrar()
        self.destroy()


def executar() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    App().mainloop()

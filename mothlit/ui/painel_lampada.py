"""Painel da lâmpada: liga/desliga, brilho, temperatura de cor e cor."""

from tkinter import colorchooser

import customtkinter as ctk

from ..devices import EstadoLampada, Lampada
from .comum import Atrasador, PainelBase

CORES_RAPIDAS = [
    ("#ff0000", (255, 0, 0)),
    ("#ff8000", (255, 128, 0)),
    ("#ffd000", (255, 208, 0)),
    ("#00e050", (0, 224, 80)),
    ("#00d0ff", (0, 208, 255)),
    ("#0040ff", (0, 64, 255)),
    ("#9000ff", (144, 0, 255)),
    ("#ff40b0", (255, 64, 176)),
]

NOMES_MODO = {"white": "Branco", "colour": "Colorido", "scene": "Cena", "music": "Música"}


class PainelLampada(PainelBase):
    dispositivo: Lampada | None

    def __init__(self, master, worker, mostrar_status):
        super().__init__(master, "💡 Lâmpada", worker, mostrar_status)

        linha = ctk.CTkFrame(self.corpo, fg_color="transparent")
        linha.pack(fill="x", pady=(4, 10))
        self.switch = ctk.CTkSwitch(linha, text="Ligada", command=self._alternar)
        self.switch.pack(side="left")
        self.rotulo_modo = ctk.CTkLabel(linha, text="", text_color="gray")
        self.rotulo_modo.pack(side="right")

        # Brilho
        self.rotulo_brilho = self._titulo("Brilho")
        self.slider_brilho = ctk.CTkSlider(
            self.corpo, from_=1, to=100, number_of_steps=99, command=self._brilho_movido
        )
        self.slider_brilho.pack(fill="x", pady=(0, 12))
        self._enviar_brilho = Atrasador(self, 350, self._mandar_brilho)

        # Temperatura de cor
        self.quadro_temp = ctk.CTkFrame(self.corpo, fg_color="transparent")
        self.rotulo_temp = self._titulo("Temperatura de cor", self.quadro_temp)
        self.slider_temp = ctk.CTkSlider(
            self.quadro_temp, from_=0, to=100, number_of_steps=100, command=self._temp_movida
        )
        self.slider_temp.pack(fill="x")
        legenda = ctk.CTkFrame(self.quadro_temp, fg_color="transparent")
        legenda.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(legenda, text="Quente", text_color="gray", height=16).pack(side="left")
        ctk.CTkLabel(legenda, text="Fria", text_color="gray", height=16).pack(side="right")
        self._enviar_temp = Atrasador(self, 350, self._mandar_temp)

        # Cor
        self.quadro_cor = ctk.CTkFrame(self.corpo, fg_color="transparent")
        self._titulo("Cor", self.quadro_cor)
        paleta = ctk.CTkFrame(self.quadro_cor, fg_color="transparent")
        paleta.pack(fill="x")
        botoes_cor = []
        for hexa, rgb in CORES_RAPIDAS:
            botao = ctk.CTkButton(
                paleta, text="", width=28, height=28, corner_radius=14,
                fg_color=hexa, hover_color=hexa, command=lambda c=rgb: self._mandar_cor(c),
            )
            botao.pack(side="left", padx=(0, 6))
            botoes_cor.append(botao)
        self.botao_outra = ctk.CTkButton(paleta, text="Outra…", width=70, command=self._escolher_cor)
        self.botao_outra.pack(side="left")

        self._controles = [self.switch, self.slider_brilho, self.slider_temp, self.botao_outra, *botoes_cor]

    def _titulo(self, texto, master=None):
        rotulo = ctk.CTkLabel(master or self.corpo, text=texto, anchor="w", height=20)
        rotulo.pack(fill="x")
        return rotulo

    # --- estado vindo do aparelho ---

    def aplicar_estado(self, estado: EstadoLampada) -> None:
        self.switch.select() if estado.ligada else self.switch.deselect()
        self.rotulo_modo.configure(text=NOMES_MODO.get(estado.modo, estado.modo))
        self.slider_brilho.set(max(estado.brilho, 1))
        self.rotulo_brilho.configure(text=f"Brilho  {estado.brilho}%")

        if estado.suporta_temperatura:
            self.quadro_temp.pack(fill="x")
            if estado.temperatura_cor is not None:
                self.slider_temp.set(estado.temperatura_cor)
        else:
            self.quadro_temp.pack_forget()

        if estado.suporta_cor:
            self.quadro_cor.pack(fill="x")
        else:
            self.quadro_cor.pack_forget()

    def habilitar(self, ativo: bool) -> None:
        for controle in self._controles:
            controle.configure(state="normal" if ativo else "disabled")

    # --- ações do usuário ---

    def _alternar(self) -> None:
        if self.switch.get():
            self.comando(self.dispositivo.ligar, "Lâmpada ligada")
        else:
            self.comando(self.dispositivo.desligar, "Lâmpada desligada")

    def _brilho_movido(self, valor: float) -> None:
        self.registrar_interacao()
        self.rotulo_brilho.configure(text=f"Brilho  {round(valor)}%")
        self._enviar_brilho.disparar()

    def _mandar_brilho(self) -> None:
        valor = round(self.slider_brilho.get())
        self.comando(lambda: self.dispositivo.definir_brilho(valor), f"Brilho em {valor}%")

    def _temp_movida(self, _valor: float) -> None:
        self.registrar_interacao()
        self._enviar_temp.disparar()

    def _mandar_temp(self) -> None:
        valor = round(self.slider_temp.get())
        self.comando(lambda: self.dispositivo.definir_temperatura_cor(valor), "Temperatura de cor ajustada")

    def _mandar_cor(self, rgb: tuple[int, int, int]) -> None:
        self.comando(lambda: self.dispositivo.definir_cor(*rgb), "Cor alterada")

    def _escolher_cor(self) -> None:
        rgb, _ = colorchooser.askcolor(title="Cor da lâmpada", parent=self)
        if rgb:
            self._mandar_cor(tuple(int(c) for c in rgb))

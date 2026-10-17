"""Componentes visuais reutilizáveis."""

import math
from typing import Callable

import customtkinter as ctk
from customtkinter.windows.widgets.core_widget_classes import DropdownMenu
from PIL import ImageTk

from . import desenhos, tema


class BotaoIcone(ctk.CTkButton):
    """Botão redondo só com ícone."""

    def __init__(self, master, codigo: str, comando: Callable | None = None, tamanho: int = 36,
                 tamanho_icone: int = 16, fundo: str = tema.BLOCO, **kwargs):
        self._codigo = codigo
        self._tamanho_icone = tamanho_icone
        super().__init__(
            master, text="", width=tamanho, height=tamanho, corner_radius=tamanho // 2,
            fg_color=fundo, hover_color=tema.BLOCO_HOVER, border_width=1, border_color=tema.BLOCO_BORDA,
            image=tema.icone(codigo, tamanho_icone, tema.TEXTO), command=comando, **kwargs,
        )

    def _create_grid(self):
        # O CTkButton reserva `corner_radius` de cada lado do conteúdo, o que alarga botões
        # redondos (vira pílula). Aqui o ícone fica centralizado, então zeramos essa reserva.
        super()._create_grid()
        minimo = self._apply_widget_scaling(self._border_width + 1)
        self.grid_columnconfigure(0, minsize=minimo)
        self.grid_columnconfigure(4, minsize=minimo)

    def destacar(self, ativo: bool) -> None:
        """Botão de energia: ciano quando ligado."""
        cor_icone = tema.TEXTO_SOBRE_DESTAQUE if ativo else tema.TEXTO_SUAVE
        self.configure(
            fg_color=tema.DESTAQUE if ativo else tema.BLOCO,
            hover_color=tema.DESTAQUE_HOVER if ativo else tema.BLOCO_HOVER,
            border_color=tema.DESTAQUE if ativo else tema.BLOCO_BORDA,
            image=tema.icone(self._codigo, self._tamanho_icone, cor_icone),
        )


class Abas(ctk.CTkFrame):
    """Abas em formato de pílula; a ativa fica ciano."""

    def __init__(self, master, nomes: list[str], ao_trocar: Callable[[str], None], altura: int = 40):
        super().__init__(master, fg_color="transparent")
        self._ao_trocar = ao_trocar
        self._botoes: dict[str, ctk.CTkButton] = {}
        for i, nome in enumerate(nomes):
            botao = ctk.CTkButton(
                self, text=nome, height=altura, corner_radius=altura // 2, font=tema.fonte(13),
                border_width=1, command=lambda n=nome: self.selecionar(n),
            )
            botao.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 5, 0 if i == len(nomes) - 1 else 5))
            self.grid_columnconfigure(i, weight=1, uniform="aba")
            self._botoes[nome] = botao
        self.atual = nomes[0]
        self._pintar()

    def selecionar(self, nome: str) -> None:
        self.atual = nome
        self._pintar()
        self._ao_trocar(nome)

    def _pintar(self) -> None:
        for nome, botao in self._botoes.items():
            ativo = nome == self.atual
            botao.configure(
                fg_color=tema.DESTAQUE if ativo else tema.BLOCO,
                hover_color=tema.DESTAQUE_HOVER if ativo else tema.BLOCO_HOVER,
                text_color=tema.TEXTO_SOBRE_DESTAQUE if ativo else tema.TEXTO,
                border_color=tema.DESTAQUE if ativo else tema.BLOCO_BORDA,
            )


class Bloco(ctk.CTkFrame):
    """Bloco quadrado (ícone, título, valor) que abre um menu de opções ao clicar."""

    def __init__(self, master, codigo_icone: str, titulo: str, ao_escolher: Callable[[str], None]):
        super().__init__(master, fg_color=tema.BLOCO, corner_radius=14, border_width=1,
                         border_color=tema.BLOCO_BORDA, height=92)
        self.grid_propagate(False)
        self._codigo = codigo_icone
        self._ao_escolher = ao_escolher
        self._opcoes: dict[str, str] = {}  # nome exibido -> valor da API
        self._ativo = True

        self.icone = ctk.CTkLabel(self, text="", image=tema.icone(codigo_icone, 18, tema.DESTAQUE))
        self.icone.place(x=12, y=10)
        self.seta = ctk.CTkLabel(self, text="", image=tema.icone(tema.ICONE_SETA_BAIXO, 10, tema.TEXTO_SUAVE))
        self.seta.place(relx=1, x=-12, y=12, anchor="ne")
        self.titulo = ctk.CTkLabel(self, text=titulo, font=tema.fonte(12), text_color=tema.TEXTO_SUAVE, height=16)
        self.titulo.place(x=12, y=44)
        self.valor = ctk.CTkLabel(self, text="–", font=tema.fonte(13), text_color=tema.TEXTO, height=18)
        self.valor.place(x=12, y=62)

        self._menu = DropdownMenu(self, values=[], command=self._escolhido, fg_color=tema.BLOCO,
                                  hover_color=tema.BLOCO_HOVER, text_color=tema.TEXTO, font=tema.fonte(12))
        for w in (self, self.icone, self.seta, self.titulo, self.valor):
            w.bind("<Button-1>", self._abrir)
            w.bind("<Enter>", lambda _e: self._hover(True))
            w.bind("<Leave>", lambda _e: self._hover(False))

    def definir(self, opcoes: dict[str, str], atual: str | None, icone: str | None = None) -> None:
        """Atualiza opções e valor exibido. Sem opções, o bloco aparece como indisponível."""
        self._opcoes = opcoes
        if icone:
            self._codigo = icone
        self.valor.configure(text=atual if opcoes and atual else "Indisponível")
        self._menu.configure(values=list(opcoes))
        self.habilitar(self._ativo)

    def habilitar(self, ativo: bool) -> None:
        self._ativo = ativo
        usavel = ativo and len(self._opcoes) > 0
        self.valor.configure(text_color=tema.TEXTO if usavel else tema.TEXTO_APAGADO)
        self.titulo.configure(text_color=tema.TEXTO_SUAVE if usavel else tema.TEXTO_APAGADO)
        self.icone.configure(image=tema.icone(self._codigo, 18, tema.DESTAQUE if usavel else tema.TEXTO_APAGADO))
        if usavel and len(self._opcoes) > 1:
            self.seta.place(relx=1, x=-12, y=12, anchor="ne")
        else:
            self.seta.place_forget()
        if not usavel:
            self.configure(fg_color=tema.BLOCO)

    def _usavel(self) -> bool:
        return self._ativo and len(self._opcoes) > 0

    def _abrir(self, _evento=None) -> None:
        if self._usavel() and len(self._opcoes) > 1:
            self._menu.open(self.winfo_rootx(), self.winfo_rooty() + self.winfo_height() + 4)

    def _escolhido(self, nome: str) -> None:
        if nome in self._opcoes:
            self.valor.configure(text=nome)
            self._ao_escolher(self._opcoes[nome])

    def _hover(self, dentro: bool) -> None:
        if self._usavel():
            self.configure(fg_color=tema.BLOCO_HOVER if dentro else tema.BLOCO)


class DiscoCores(ctk.CTkCanvas):
    """Disco de cores: ângulo = matiz, distância do centro = saturação.

    O brilho fica num slider separado. Chama `ao_soltar(h, s)` ao terminar o arraste.
    """

    def __init__(self, master, ao_soltar: Callable[[float, float], None], diametro: int = 200,
                 fundo: str = tema.FUNDO):
        # Canvas não acompanha a escala do Windows sozinho; os outros widgets sim.
        escala = ctk.ScalingTracker.get_widget_scaling(master)
        self._d = int(diametro * escala)
        self._m = int(10 * escala)  # margem para o marcador não ser cortado na borda
        lado = self._d + 2 * self._m
        super().__init__(master, width=lado, height=lado, bg=fundo, highlightthickness=0)
        self._ao_soltar = ao_soltar
        self.h, self.s = 0.0, 0.0
        self._arrastando = False
        self._ativo = True

        self._img = ImageTk.PhotoImage(desenhos.disco_cores(self._d, fundo))
        self.create_image(self._m, self._m, image=self._img, anchor="nw")
        self._sombra = self.create_oval(0, 0, 0, 0, outline="#09090b", width=4)
        self._marca = self.create_oval(0, 0, 0, 0, outline="white", width=2)
        self._posicionar()

        self.bind("<ButtonPress-1>", self._pressionar)
        self.bind("<B1-Motion>", self._mover)
        self.bind("<ButtonRelease-1>", self._soltar)

    def definir(self, h: float, s: float) -> None:
        if not self._arrastando:
            self.h, self.s = h, s
            self._posicionar()

    def habilitar(self, ativo: bool) -> None:
        self._ativo = ativo

    def _posicionar(self) -> None:
        c = self._m + self._d / 2
        r = self.s * self._d / 2
        x, y = c + math.sin(self.h * math.tau) * r, c - math.cos(self.h * math.tau) * r
        self.coords(self._sombra, x - 9, y - 9, x + 9, y + 9)
        self.coords(self._marca, x - 8, y - 8, x + 8, y + 8)

    def _pressionar(self, e) -> None:
        c = self._m + self._d / 2
        if self._ativo and math.hypot(e.x - c, e.y - c) <= self._d / 2 + self._m:
            self._arrastando = True
            self._mover(e)

    def _mover(self, e) -> None:
        if not self._arrastando:
            return
        c = self._m + self._d / 2
        dx, dy = e.x - c, e.y - c
        self.h = (math.atan2(dx, -dy) / math.tau) % 1.0
        self.s = min(1.0, math.hypot(dx, dy) / (self._d / 2))
        self._posicionar()

    def _soltar(self, _e) -> None:
        if self._arrastando:
            self._arrastando = False
            self._ao_soltar(self.h, self.s)
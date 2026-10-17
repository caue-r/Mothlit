"""Componentes visuais reutilizáveis."""

import colorsys
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


class RodaCores(ctk.CTkCanvas):
    """Anel de matiz + quadrado de saturação/brilho. Chama `ao_soltar(h, s, v)` ao terminar o arraste."""

    def __init__(self, master, ao_soltar: Callable[[float, float, float], None], diametro: int = 220,
                 espessura: int = 22, fundo: str = tema.FUNDO):
        # Canvas não acompanha a escala do Windows sozinho; os outros widgets sim.
        escala = ctk.ScalingTracker.get_widget_scaling(master)
        diametro, espessura = int(diametro * escala), int(espessura * escala)
        super().__init__(master, width=diametro, height=diametro, bg=fundo, highlightthickness=0)
        self._ao_soltar = ao_soltar
        self._d = diametro
        self._esp = espessura
        self._lado = int((diametro / 2 - espessura - 10) * math.sqrt(2))
        self._q0 = (diametro - self._lado) / 2
        self.h, self.s, self.v = 0.0, 1.0, 1.0
        self._arrastando: str | None = None
        self._ativo = True

        self._img_anel = ImageTk.PhotoImage(desenhos.anel_matiz(diametro, espessura, fundo))
        self.create_image(0, 0, image=self._img_anel, anchor="nw")
        self._img_quadrado = None
        self._id_quadrado = self.create_image(self._q0, self._q0, anchor="nw")
        self._marca_anel = self.create_oval(0, 0, 0, 0, outline="white", width=3)
        self._marca_quadrado = self.create_oval(0, 0, 0, 0, outline="white", width=3)
        self._desenhar_quadrado()
        self._posicionar_marcas()

        self.bind("<ButtonPress-1>", self._pressionar)
        self.bind("<B1-Motion>", self._mover)
        self.bind("<ButtonRelease-1>", self._soltar)

    def definir(self, h: float, s: float, v: float) -> None:
        if self._arrastando:
            return
        mudou_matiz = abs(h - self.h) > 1e-3
        self.h, self.s, self.v = h, s, v
        if mudou_matiz:
            self._desenhar_quadrado()
        self._posicionar_marcas()

    def habilitar(self, ativo: bool) -> None:
        self._ativo = ativo

    def _desenhar_quadrado(self) -> None:
        self._img_quadrado = ImageTk.PhotoImage(desenhos.quadrado_sv(self._lado, self.h))
        self.itemconfigure(self._id_quadrado, image=self._img_quadrado)

    def _posicionar_marcas(self) -> None:
        c = self._d / 2
        r = c - self._esp / 2
        ang = self.h * math.tau
        x, y = c + math.sin(ang) * r, c - math.cos(ang) * r
        self.coords(self._marca_anel, x - 8, y - 8, x + 8, y + 8)
        qx = self._q0 + self.s * self._lado
        qy = self._q0 + (1 - self.v) * self._lado
        self.coords(self._marca_quadrado, qx - 7, qy - 7, qx + 7, qy + 7)

    def _pressionar(self, e) -> None:
        if not self._ativo:
            return
        c = self._d / 2
        r = math.hypot(e.x - c, e.y - c)
        if c - self._esp - 4 <= r <= c + 2:
            self._arrastando = "anel"
        elif self._q0 <= e.x <= self._q0 + self._lado and self._q0 <= e.y <= self._q0 + self._lado:
            self._arrastando = "quadrado"
        self._mover(e)

    def _mover(self, e) -> None:
        if self._arrastando == "anel":
            c = self._d / 2
            self.h = (math.atan2(e.x - c, -(e.y - c)) / math.tau) % 1.0
            self._desenhar_quadrado()
        elif self._arrastando == "quadrado":
            self.s = min(1.0, max(0.0, (e.x - self._q0) / self._lado))
            self.v = min(1.0, max(0.0, 1 - (e.y - self._q0) / self._lado))
        self._posicionar_marcas()

    def _soltar(self, _e) -> None:
        if self._arrastando:
            self._arrastando = None
            self._ao_soltar(self.h, self.s, self.v)

    @property
    def rgb(self) -> tuple[int, int, int]:
        return tuple(int(c * 255) for c in colorsys.hsv_to_rgb(self.h, self.s, self.v))

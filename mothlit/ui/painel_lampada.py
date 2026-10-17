"""Painel da lâmpada: quarto ilustrado, roda de cores e ajustes de branco."""

import colorsys
from functools import lru_cache

import customtkinter as ctk

from ..devices import EstadoLampada, Lampada
from . import desenhos, tema
from .comum import Atrasador, PainelBase
from .widgets import Abas, RodaCores

ILUSTRACAO = (324, 180)  # mesma proporção do desenho (360x200)
PRESETS_BRANCO = [("Quente", 0), ("Neutro", 50), ("Frio", 100)]


@lru_cache(maxsize=32)
def _imagem_quarto(ligada: bool, cor: tuple[int, int, int], intensidade: float) -> ctk.CTkImage:
    img = desenhos.quarto(ligada, cor, intensidade)
    return ctk.CTkImage(light_image=img, dark_image=img, size=ILUSTRACAO)


class PainelLampada(PainelBase):
    dispositivo: Lampada | None

    def __init__(self, master, worker, mostrar_status):
        super().__init__(master, "Lâmpada", worker, mostrar_status)
        self._estado: EstadoLampada | None = None

        self.ilustracao = ctk.CTkLabel(self.card, text="", image=_imagem_quarto(False, (255, 255, 255), 1.0))
        self.ilustracao.pack(padx=16, pady=(8, 0))
        self.legenda = ctk.CTkLabel(self.card, text="", font=tema.fonte(11), text_color=tema.TEXTO_SUAVE, height=18)
        self.legenda.pack(pady=(4, 12))

        self.abas = Abas(self, ["Cores", "Branco"], self._trocar_aba)
        self.abas.pack(fill="x", pady=(12, 8))
        self.paginas = ctk.CTkFrame(self, fg_color="transparent")
        self.paginas.pack(fill="both", expand=True)

        # Página "Cores": roda de matiz + quadrado de saturação/brilho
        self.pagina_cores = ctk.CTkFrame(self.paginas, fg_color="transparent")
        self.roda = RodaCores(self.pagina_cores, self._cor_escolhida, diametro=196, fundo=tema.FUNDO)
        self.roda.pack(pady=(6, 0))

        # Página "Branco": brilho, temperatura e atalhos
        self.pagina_branco = ctk.CTkFrame(self.paginas, fg_color="transparent")
        self.rotulo_brilho = self._rotulo(self.pagina_branco, "Brilho")
        self.slider_brilho = self._slider(self.pagina_branco, 1, 100, self._brilho_movido)
        self._enviar_brilho = Atrasador(self, 350, self._mandar_brilho)

        self.quadro_temp = ctk.CTkFrame(self.pagina_branco, fg_color="transparent")
        self.quadro_temp.pack(fill="x")
        self._rotulo(self.quadro_temp, "Temperatura de cor")
        self.slider_temp = self._slider(self.quadro_temp, 0, 100, self._temp_movida)
        presets = ctk.CTkFrame(self.quadro_temp, fg_color="transparent")
        presets.pack(fill="x", pady=(4, 0))
        self._botoes_preset = []
        for i, (nome, valor) in enumerate(PRESETS_BRANCO):
            cor = "#%02x%02x%02x" % desenhos.cor_do_branco(valor)
            botao = ctk.CTkButton(
                presets, text=nome, height=34, corner_radius=17, font=tema.fonte(12), fg_color=tema.BLOCO,
                hover_color=tema.BLOCO_HOVER, border_width=1, border_color=cor, text_color=tema.TEXTO,
                command=lambda v=valor: self._mandar_temp(v),
            )
            botao.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 4, 0 if i == 2 else 4))
            presets.grid_columnconfigure(i, weight=1, uniform="preset")
            self._botoes_preset.append(botao)
        self._enviar_temp = Atrasador(self, 350, lambda: self._mandar_temp(round(self.slider_temp.get())))

        self._trocar_aba("Cores")

    def _rotulo(self, master, texto):
        rotulo = ctk.CTkLabel(master, text=texto, font=tema.fonte(12), text_color=tema.TEXTO_SUAVE, anchor="w",
                              height=18)
        rotulo.pack(fill="x", padx=4, pady=(8, 0))
        return rotulo

    def _slider(self, master, de, ate, comando):
        slider = ctk.CTkSlider(master, from_=de, to=ate, number_of_steps=ate - de, height=18,
                               progress_color=tema.DESTAQUE, button_color=tema.TEXTO, button_hover_color="#ffffff",
                               fg_color=tema.BLOCO_BORDA, command=comando)
        slider.pack(fill="x", pady=(4, 6))
        return slider

    def _trocar_aba(self, nome: str) -> None:
        for pagina in (self.pagina_cores, self.pagina_branco):
            pagina.pack_forget()
        (self.pagina_cores if nome == "Cores" else self.pagina_branco).pack(fill="both", expand=True)

    # --- estado vindo do aparelho ---

    def aplicar_estado(self, e: EstadoLampada) -> None:
        self._estado = e
        self.botao_energia.destacar(e.ligada)
        if not e.ligada:
            self.definir_situacao("Desligada")
            self.legenda.configure(text="Desligada")
        elif e.modo == "colour":
            self.definir_situacao("Ligada · Colorida")
            self.legenda.configure(text=f"Cor atual · {e.brilho}%")
        else:
            self.definir_situacao("Ligada · Branca")
            self.legenda.configure(text=f"Branco · {e.brilho}%")
        self._desenhar_quarto()

        self.slider_brilho.set(max(e.brilho, 1))
        self.rotulo_brilho.configure(text=f"Brilho · {e.brilho}%")
        if e.temperatura_cor is not None:
            self.slider_temp.set(e.temperatura_cor)
        if e.cor_hsv:
            self.roda.definir(*e.cor_hsv)

        if e.suporta_temperatura:
            self.quadro_temp.pack(fill="x")
        else:
            self.quadro_temp.pack_forget()
        if not e.suporta_cor and self.abas.winfo_ismapped():
            self.abas.pack_forget()
            self._trocar_aba("Branco")

    def _desenhar_quarto(self, cor=None, intensidade=None) -> None:
        e = self._estado
        if e is None:
            return
        if cor is None:
            if e.modo == "colour" and e.cor_hsv:
                h, s, _ = e.cor_hsv
                cor = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(h, s, 1))
            else:
                cor = desenhos.cor_do_branco(e.temperatura_cor if e.temperatura_cor is not None else 50)
        if intensidade is None:
            intensidade = e.brilho / 100
        # arredonda para reaproveitar o cache de imagens
        self.ilustracao.configure(image=_imagem_quarto(e.ligada, tuple(c // 8 * 8 for c in cor),
                                                       round(intensidade, 1)))

    def habilitar(self, ativo: bool) -> None:
        estado = "normal" if ativo else "disabled"
        for w in (self.botao_energia, self.slider_brilho, self.slider_temp, *self._botoes_preset):
            w.configure(state=estado)
        self.roda.habilitar(ativo)

    # --- ações do usuário ---

    def _energia(self) -> None:
        ligada = bool(self._estado and self._estado.ligada)
        if ligada:
            self.comando(self.dispositivo.desligar, "Lâmpada desligada")
        else:
            self.comando(self.dispositivo.ligar, "Lâmpada ligada")
        self.botao_energia.destacar(not ligada)

    def _cor_escolhida(self, h: float, s: float, v: float) -> None:
        if self.dispositivo is None:
            return
        rgb = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(h, s, 1))
        if self._estado:
            self._estado.ligada = True
            self._estado.modo = "colour"
            self._estado.brilho = round(v * 100)
        self._desenhar_quarto(rgb, v)
        self.comando(lambda: self.dispositivo.definir_hsv(h, s, v), "Cor alterada")

    def _brilho_movido(self, valor: float) -> None:
        self.registrar_interacao()
        self.rotulo_brilho.configure(text=f"Brilho · {round(valor)}%")
        self._desenhar_quarto(intensidade=valor / 100)
        self._enviar_brilho.disparar()

    def _mandar_brilho(self) -> None:
        valor = round(self.slider_brilho.get())
        self.comando(lambda: self.dispositivo.definir_brilho(valor), f"Brilho em {valor}%")

    def _temp_movida(self, valor: float) -> None:
        self.registrar_interacao()
        if self._estado and self._estado.modo != "colour":
            self._desenhar_quarto(cor=desenhos.cor_do_branco(round(valor)))
        self._enviar_temp.disparar()

    def _mandar_temp(self, valor: int) -> None:
        self.slider_temp.set(valor)
        self.comando(lambda: self.dispositivo.definir_temperatura_cor(valor), "Temperatura de cor ajustada")

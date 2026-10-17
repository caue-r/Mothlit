"""Painel da lâmpada: quarto ilustrado, brilho, disco de cores e ajustes de branco."""

import colorsys
from functools import lru_cache

import customtkinter as ctk

from ..devices import EstadoLampada, Lampada
from . import desenhos, tema
from .comum import Atrasador, PainelBase
from .widgets import Abas, DiscoCores

ILUSTRACAO = (324, 180)  # mesma proporção do desenho (360x200)
PRESETS_BRANCO = [("Quente", 0), ("Neutro", 50), ("Frio", 100)]


@lru_cache(maxsize=32)
def _imagem_quarto(ligada: bool, cor: tuple[int, int, int], intensidade: float) -> ctk.CTkImage:
    img = desenhos.quarto(ligada, cor, intensidade)
    return ctk.CTkImage(light_image=img, dark_image=img, size=ILUSTRACAO)


def _slider(master, de, ate, comando) -> ctk.CTkSlider:
    return ctk.CTkSlider(master, from_=de, to=ate, number_of_steps=ate - de, height=16,
                         progress_color=tema.DESTAQUE, button_color=tema.DESTAQUE,
                         button_hover_color=tema.DESTAQUE_HOVER, fg_color=tema.TRILHO, command=comando)


class PainelLampada(PainelBase):
    dispositivo: Lampada | None

    def __init__(self, master, worker, mostrar_status):
        super().__init__(master, "Lâmpada", worker, mostrar_status)
        self._estado: EstadoLampada | None = None

        self.ilustracao = ctk.CTkLabel(self.card, text="", image=_imagem_quarto(False, (255, 255, 255), 1.0))
        self.ilustracao.pack(padx=16, pady=(10, 0))

        # Brilho: vale para o modo branco e para o colorido
        linha = ctk.CTkFrame(self.card, fg_color="transparent")
        linha.pack(fill="x", padx=18, pady=(14, 16))
        ctk.CTkLabel(linha, text="", image=tema.icone(tema.ICONE_SOL, 16, tema.TEXTO_SUAVE)).pack(side="left")
        self.rotulo_brilho = ctk.CTkLabel(linha, text="–", width=40, font=tema.fonte(12), text_color=tema.TEXTO,
                                          anchor="e")
        self.rotulo_brilho.pack(side="right")
        self.slider_brilho = _slider(linha, 1, 100, self._brilho_movido)
        self.slider_brilho.pack(side="left", fill="x", expand=True, padx=12)
        self._enviar_brilho = Atrasador(self, 350, self._mandar_brilho)

        self.abas = Abas(self, ["Cores", "Branco"], self._trocar_aba, altura=36)
        self.abas.pack(fill="x", pady=(14, 6))
        self.paginas = ctk.CTkFrame(self, fg_color="transparent")
        self.paginas.pack(fill="both", expand=True)

        # Página "Cores"
        self.pagina_cores = ctk.CTkFrame(self.paginas, fg_color="transparent")
        self.disco = DiscoCores(self.pagina_cores, self._cor_escolhida, diametro=168, fundo=tema.FUNDO)
        self.disco.pack(pady=(4, 0))

        # Página "Branco"
        self.pagina_branco = ctk.CTkFrame(self.paginas, fg_color="transparent")
        legenda = ctk.CTkFrame(self.pagina_branco, fg_color="transparent")
        legenda.pack(fill="x", padx=2, pady=(14, 0))
        ctk.CTkLabel(legenda, text="Quente", font=tema.fonte(11), text_color=tema.TEXTO_SUAVE, height=16).pack(
            side="left")
        ctk.CTkLabel(legenda, text="Frio", font=tema.fonte(11), text_color=tema.TEXTO_SUAVE, height=16).pack(
            side="right")
        self.slider_temp = _slider(self.pagina_branco, 0, 100, self._temp_movida)
        self.slider_temp.pack(fill="x", pady=(6, 14))
        presets = ctk.CTkFrame(self.pagina_branco, fg_color="transparent")
        presets.pack(fill="x")
        self._botoes_preset = []
        for i, (nome, valor) in enumerate(PRESETS_BRANCO):
            botao = ctk.CTkButton(
                presets, text=nome, height=36, corner_radius=18, font=tema.fonte(12), fg_color=tema.BLOCO,
                hover_color=tema.BLOCO_HOVER, border_width=1, border_color=tema.BLOCO_BORDA, text_color=tema.TEXTO,
                command=lambda v=valor: self._mandar_temp(v),
            )
            botao.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 4, 0 if i == 2 else 4))
            presets.grid_columnconfigure(i, weight=1, uniform="preset")
            self._botoes_preset.append(botao)
        self._enviar_temp = Atrasador(self, 350, lambda: self._mandar_temp(round(self.slider_temp.get())))

        self._trocar_aba("Cores")

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
        else:
            self.definir_situacao("Ligada · " + ("Colorida" if e.modo == "colour" else "Branca"))
        self._mostrar_brilho(e.brilho)
        if e.temperatura_cor is not None:
            self.slider_temp.set(e.temperatura_cor)
        if e.cor_hsv:
            self.disco.definir(e.cor_hsv[0], e.cor_hsv[1])
        self._desenhar_quarto()

        if not e.suporta_cor and self.abas.winfo_ismapped():
            self.abas.pack_forget()
            self._trocar_aba("Branco")
        if not e.suporta_temperatura:
            self.pagina_branco.pack_forget()

    def _mostrar_brilho(self, valor: int) -> None:
        self.slider_brilho.set(max(valor, 1))
        self.rotulo_brilho.configure(text=f"{valor}%")

    def _desenhar_quarto(self) -> None:
        e = self._estado
        if e is None:
            return
        if e.modo == "colour" and e.cor_hsv:
            h, s, _ = e.cor_hsv
            cor = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(h, s, 1))
        else:
            cor = desenhos.cor_do_branco(e.temperatura_cor if e.temperatura_cor is not None else 50)
        # arredonda para reaproveitar o cache de imagens
        self.ilustracao.configure(image=_imagem_quarto(e.ligada, tuple(c // 8 * 8 for c in cor),
                                                       round(e.brilho / 100, 1)))

    def habilitar(self, ativo: bool) -> None:
        estado = "normal" if ativo else "disabled"
        for w in (self.botao_energia, self.slider_brilho, self.slider_temp, *self._botoes_preset):
            w.configure(state=estado)
        self.disco.habilitar(ativo)

    # --- ações do usuário (atualizam a ilustração na hora; a releitura confirma) ---

    def _energia(self) -> None:
        ligada = bool(self._estado and self._estado.ligada)
        if ligada:
            self.comando(self.dispositivo.desligar, "Lâmpada desligada")
        else:
            self.comando(self.dispositivo.ligar, "Lâmpada ligada")
        if self._estado:
            self._estado.ligada = not ligada
            self._desenhar_quarto()
        self.botao_energia.destacar(not ligada)

    def _cor_escolhida(self, h: float, s: float) -> None:
        if self.dispositivo is None:
            return
        v = self.slider_brilho.get() / 100
        if self._estado:
            self._estado.ligada, self._estado.modo, self._estado.cor_hsv = True, "colour", (h, s, v)
            self._desenhar_quarto()
        self.comando(lambda: self.dispositivo.definir_hsv(h, s, v), "Cor alterada")

    def _brilho_movido(self, valor: float) -> None:
        self.registrar_interacao()
        self.rotulo_brilho.configure(text=f"{round(valor)}%")
        if self._estado:
            self._estado.brilho = round(valor)
            self._desenhar_quarto()
        self._enviar_brilho.disparar()

    def _mandar_brilho(self) -> None:
        valor = round(self.slider_brilho.get())
        e = self._estado
        if e and e.modo == "colour" and e.cor_hsv:
            # no modo colorido o brilho é o V do HSV: mantém a cor e muda só a intensidade
            h, s, _ = e.cor_hsv
            self.comando(lambda: self.dispositivo.definir_hsv(h, s, valor / 100), f"Brilho em {valor}%")
        else:
            self.comando(lambda: self.dispositivo.definir_brilho(valor), f"Brilho em {valor}%")

    def _temp_movida(self, valor: float) -> None:
        self.registrar_interacao()
        if self._estado:
            self._estado.temperatura_cor = round(valor)
            if self._estado.modo != "colour":
                self._desenhar_quarto()
        self._enviar_temp.disparar()

    def _mandar_temp(self, valor: int) -> None:
        self.slider_temp.set(valor)
        if self._estado:
            self._estado.ligada, self._estado.modo, self._estado.temperatura_cor = True, "white", valor
            self._desenhar_quarto()
        self.comando(lambda: self.dispositivo.definir_temperatura_cor(valor), "Temperatura de cor ajustada")

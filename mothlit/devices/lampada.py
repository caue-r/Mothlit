"""Adaptador da lâmpada Tuya (Ekaza) via LAN com tinytuya."""

import threading
from dataclasses import dataclass

import tinytuya

from .base import ErroDispositivo

# Códigos de erro do tinytuya (tinytuya.error_codes) traduzidos para o usuário
_MENSAGENS_ERRO = {
    "901": "Lâmpada inacessível. Ela está ligada na tomada e na mesma rede?",
    "902": "A lâmpada demorou demais para responder.",
    "905": "Lâmpada inacessível. Ela está ligada na tomada e na mesma rede?",
    "914": "A lâmpada recusou a conexão: confira a local_key e a versão do protocolo.",
}


@dataclass
class EstadoLampada:
    ligada: bool
    modo: str  # "white", "colour", "scene" ou "music"
    brilho: int  # 0-100 %
    temperatura_cor: int | None  # 0-100 % (0 = quente, 100 = fria)
    cor_rgb: tuple[int, int, int] | None
    suporta_temperatura: bool
    suporta_cor: bool
    cor_hsv: tuple[float, float, float] | None = None  # cada componente de 0 a 1


class Lampada:
    nome = "Lâmpada"

    def __init__(
        self,
        device_id: str,
        ip: str,
        local_key: str,
        versao: float,
        timeout: float = 2.0,
        bulb: tinytuya.BulbDevice | None = None,
    ):
        # Padrão do tinytuya é 5 s x 5 tentativas (até 45 s). Aqui o pior caso fica em ~5 s.
        self._bulb = bulb or tinytuya.BulbDevice(
            device_id,
            ip,
            local_key,
            version=versao,
            connection_timeout=timeout,
            connection_retry_limit=2,
            connection_retry_delay=1,
        )
        # O socket do tinytuya não é thread-safe: um comando por vez.
        self._lock = threading.Lock()

    # --- comandos ---

    def ligar(self) -> None:
        self._executar(self._bulb.turn_on)

    def desligar(self) -> None:
        self._executar(self._bulb.turn_off)

    def definir_brilho(self, porcentagem: int) -> None:
        # 0 % no tinytuya desliga a lâmpada; o mínimo útil é 1 %.
        self._executar(self._bulb.set_brightness_percentage, _limitar(porcentagem, 1, 100))

    def definir_temperatura_cor(self, porcentagem: int) -> None:
        self._executar(self._bulb.set_colourtemp_percentage, _limitar(porcentagem, 0, 100))

    def definir_cor(self, r: int, g: int, b: int) -> None:
        self._executar(self._bulb.set_colour, *(_limitar(c, 0, 255) for c in (r, g, b)))

    def definir_hsv(self, h: float, s: float, v: float) -> None:
        """Cor por matiz/saturação/brilho, cada um de 0 a 1 (usado pela roda de cores)."""
        h, s, v = (max(0.0, min(1.0, float(x))) for x in (h, s, v))
        self._executar(self._bulb.set_hsv, h, s, max(v, 0.01))

    # --- leitura ---

    def estado(self) -> EstadoLampada:
        with self._lock:
            status = _checar(self._chamar(self._bulb.status))
            if not self._bulb.bulb_configured:
                self._bulb.detect_bulb(response=status)
            if not self._bulb.bulb_configured:
                raise ErroDispositivo("Não reconheci este aparelho como lâmpada (DPS inesperados).")

            dps = status.get("dps", {})
            dpset = self._bulb.dpset
            maximo = self._valor_max()

            def dp(recurso):
                chave = dpset.get(recurso)
                return dps.get(chave) if chave else None

            modo = dp("mode") or "white"
            suporta_temp = bool(dpset.get("colourtemp"))
            suporta_cor = bool(dpset.get("colour"))

            cor = hsv = None
            hexcor = dp("colour")
            if suporta_cor and isinstance(hexcor, str) and hexcor:
                try:
                    cor = tinytuya.BulbDevice.hexvalue_to_rgb(hexcor, dpset.get("value_hexformat"))
                    hsv = tinytuya.BulbDevice.hexvalue_to_hsv(hexcor, dpset.get("value_hexformat"))
                except (ValueError, IndexError):
                    cor = hsv = None

            # No modo colorido o brilho mora no V do HSV, não no DP de brilho.
            if modo == "colour" and isinstance(hexcor, str) and hexcor:
                try:
                    _, _, v = tinytuya.BulbDevice.hexvalue_to_hsv(hexcor, dpset.get("value_hexformat"))
                    brilho = round(v * 100)
                except (ValueError, IndexError):
                    brilho = 0
            else:
                brilho = _porcentagem(dp("brightness"), maximo)

            temp = dp("colourtemp")
            return EstadoLampada(
                ligada=bool(dp("switch")),
                modo=modo,
                brilho=brilho,
                temperatura_cor=_porcentagem(temp, maximo) if suporta_temp and temp is not None else None,
                cor_rgb=tuple(cor) if cor else None,
                suporta_temperatura=suporta_temp,
                suporta_cor=suporta_cor,
                cor_hsv=tuple(hsv) if hsv else None,
            )

    # --- internos ---

    def _valor_max(self) -> int:
        maximo = self._bulb.dpset.get("value_max") or -1
        if maximo < 1:
            padrao = tinytuya.BulbDevice.DEFAULT_DPSET.get(self._bulb.bulb_type, {})
            maximo = padrao.get("value_max") or 1000
        return maximo

    def _executar(self, funcao, *args) -> None:
        with self._lock:
            _checar(self._chamar(funcao, *args))

    @staticmethod
    def _chamar(funcao, *args):
        try:
            return funcao(*args)
        except (ValueError, RuntimeError) as e:
            raise ErroDispositivo(f"Lâmpada: {e}") from e
        except OSError as e:
            raise ErroDispositivo(_MENSAGENS_ERRO["905"]) from e


def _checar(resposta):
    """O tinytuya devolve erros como dict {'Error', 'Err', 'Payload'} em vez de exceção."""
    if isinstance(resposta, dict) and "Error" in resposta:
        codigo = str(resposta.get("Err"))
        raise ErroDispositivo(_MENSAGENS_ERRO.get(codigo, f"Lâmpada: {resposta['Error']}"))
    return resposta if isinstance(resposta, dict) else {}


def _porcentagem(valor, maximo: int) -> int:
    if not isinstance(valor, (int, float)):
        return 0
    return _limitar(round(valor * 100 / maximo), 0, 100)


def _limitar(valor: int, minimo: int, maximo: int) -> int:
    return max(minimo, min(maximo, int(valor)))

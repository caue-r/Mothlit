"""Adaptador do ar-condicionado Samsung via SmartThings API."""

import threading
from dataclasses import dataclass, field

from .base import ErroDispositivo
from .smartthings import SmartThingsClient

CAP_SWITCH = "switch"
CAP_SETPOINT = "thermostatCoolingSetpoint"
CAP_MODO = "airConditionerMode"
CAP_VENTILADOR = "airConditionerFanMode"
CAP_TEMPERATURA = "temperatureMeasurement"
CAP_OSCILACAO = "fanOscillationMode"
CAP_OPCIONAL = "custom.airConditionerOptionalMode"  # Samsung: sleep, quiet, windFree...

FAIXA_PADRAO = (16.0, 30.0, 1.0)


@dataclass
class EstadoAr:
    ligado: bool
    temperatura_alvo: float | None
    faixa_alvo: tuple[float, float, float]  # mínimo, máximo, passo
    temperatura_ambiente: float | None
    modo: str | None
    modos: list[str] = field(default_factory=list)
    ventilador: str | None = None
    ventiladores: list[str] = field(default_factory=list)
    capabilities: set[str] = field(default_factory=set)
    oscilacao: str | None = None
    oscilacoes: list[str] = field(default_factory=list)
    modo_opcional: str | None = None
    modos_opcionais: list[str] = field(default_factory=list)
    rotulo: str = ""


class ArCondicionado:
    nome = "Ar-condicionado"

    def __init__(self, cliente: SmartThingsClient, device_id: str, componente: str = "main"):
        self._cliente = cliente
        self._id = device_id
        self._componente = componente
        self._capabilities: set[str] | None = None
        self.rotulo = ""
        self._faixa = FAIXA_PADRAO
        self._lock = threading.Lock()

    def capabilities(self) -> set[str]:
        """Capabilities declaradas pelo aparelho (lidas uma vez via GET /devices/{id})."""
        if self._capabilities is None:
            dados = self._cliente.dispositivo(self._id)
            self.rotulo = dados.get("label") or dados.get("name") or ""
            for comp in dados.get("components", []):
                if comp.get("id") == self._componente:
                    self._capabilities = {c["id"] for c in comp.get("capabilities", [])}
                    break
            else:
                raise ErroDispositivo("O ar-condicionado não tem o componente principal esperado.")
        return self._capabilities

    # --- comandos ---

    def ligar(self) -> None:
        self._executar(CAP_SWITCH, "on")

    def desligar(self) -> None:
        self._executar(CAP_SWITCH, "off")

    def definir_temperatura(self, valor: float) -> float:
        minimo, maximo, _ = self._faixa
        valor = max(minimo, min(maximo, valor))
        # A API aceita número; mandamos inteiro quando não há fração (ex.: 24, não 24.0).
        self._executar(CAP_SETPOINT, "setCoolingSetpoint", [int(valor) if valor == int(valor) else valor])
        return valor

    def definir_modo(self, modo: str) -> None:
        self._executar(CAP_MODO, "setAirConditionerMode", [modo])

    def definir_ventilador(self, velocidade: str) -> None:
        self._executar(CAP_VENTILADOR, "setFanMode", [velocidade])

    def definir_oscilacao(self, modo: str) -> None:
        self._executar(CAP_OSCILACAO, "setFanOscillationMode", [modo])

    def definir_modo_opcional(self, modo: str) -> None:
        self._executar(CAP_OPCIONAL, "setAcOptionalMode", [modo])

    # --- leitura ---

    def estado(self) -> EstadoAr:
        with self._lock:
            caps = set(self.capabilities())
            comp = self._cliente.status(self._id).get("components", {}).get(self._componente, {})

        def valor(cap, atributo):
            return ((comp.get(cap) or {}).get(atributo) or {}).get("value")

        # Algumas capabilities são declaradas mas desativadas neste modelo.
        caps -= set(valor("custom.disabledCapabilities", "disabledCapabilities") or [])

        faixa = valor(CAP_SETPOINT, "coolingSetpointRange")
        if isinstance(faixa, dict) and "minimum" in faixa and "maximum" in faixa:
            self._faixa = (float(faixa["minimum"]), float(faixa["maximum"]), float(faixa.get("step") or 1))

        # "available*" muda conforme o modo atual (ex.: em auto só há ventilador auto);
        # "supported*" é a lista completa do aparelho.
        modos = valor(CAP_MODO, "availableAcModes") or valor(CAP_MODO, "supportedAcModes") or []
        ventiladores = (
            valor(CAP_VENTILADOR, "availableAcFanModes") or valor(CAP_VENTILADOR, "supportedAcFanModes") or []
        )

        return EstadoAr(
            ligado=valor(CAP_SWITCH, "switch") == "on",
            temperatura_alvo=_numero(valor(CAP_SETPOINT, "coolingSetpoint")),
            faixa_alvo=self._faixa,
            temperatura_ambiente=_numero(valor(CAP_TEMPERATURA, "temperature")),
            modo=valor(CAP_MODO, "airConditionerMode"),
            modos=list(modos),
            ventilador=valor(CAP_VENTILADOR, "fanMode"),
            ventiladores=list(ventiladores),
            capabilities=caps,
            oscilacao=valor(CAP_OSCILACAO, "fanOscillationMode"),
            oscilacoes=list(
                valor(CAP_OSCILACAO, "availableFanOscillationModes")
                or valor(CAP_OSCILACAO, "supportedFanOscillationModes")
                or []
            ),
            modo_opcional=valor(CAP_OPCIONAL, "acOptionalMode"),
            modos_opcionais=list(
                valor(CAP_OPCIONAL, "availableAcOptionalMode") or valor(CAP_OPCIONAL, "supportedAcOptionalMode") or []
            ),
            rotulo=self.rotulo,
        )

    # --- internos ---

    def _executar(self, capability: str, comando: str, argumentos: list | None = None) -> None:
        with self._lock:
            if capability not in self.capabilities():
                raise ErroDispositivo(f"O ar-condicionado não suporta '{capability}'.")
            self._cliente.executar(self._id, capability, comando, argumentos, self._componente)


def _numero(valor) -> float | None:
    return float(valor) if isinstance(valor, (int, float)) else None

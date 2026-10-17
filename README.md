# Mothlit

App desktop pessoal para controlar pelo PC, sem passar pela Alexa:

- **Lâmpada Ekaza** (plataforma Tuya / Smart Life): controle **local** pela LAN com [tinytuya](https://github.com/jasonacox/tinytuya).
- **Ar-condicionado Samsung**: [SmartThings REST API](https://developer.smartthings.com/docs/api/public).

## Instalação

Usa [uv](https://docs.astral.sh/uv/). Ele instala o Python 3.12 se for preciso e trava as versões no `uv.lock`, então o ambiente é reproduzível.

```powershell
uv sync
uv run pytest            # testes (não precisam dos aparelhos)
```

## Configuração

```powershell
uv run python -m mothlit setup
```

O setup grava:

- o que não é sensível (IDs, IP, versão do protocolo) em `%APPDATA%\Mothlit\.env` (modelo em `.env.example`);
- os segredos (`local_key` da lâmpada e token da SmartThings) no **keyring** do Windows (Gerenciador de Credenciais › Credenciais do Windows › `mothlit`).

### Lâmpada (Tuya)

O controle local precisa de `device_id`, `local_key`, IP e **versão do protocolo**. A `local_key` só sai da nuvem Tuya, então é preciso uma conta de desenvolvedor uma única vez:

1. Crie uma conta em [iot.tuya.com](https://iot.tuya.com) › *Cloud › Development › Create Cloud Project*. Escolha o data center da sua conta Smart Life (no Brasil costuma ser *Western America*, região `us`).
2. Em *Devices › Link App Account*, escaneie o QR code com o app Smart Life.
3. Anote o **Access ID** e o **Access Secret** do projeto.

No setup, escolha:

- **Opção 1 (automática)**: informe Access ID, Access Secret e região. O Mothlit busca o `device_id` e a `local_key` na nuvem e procura IP e versão na rede local. O Access Secret não é salvo.
- **Opção 2 (manual)**: rode `uv run python -m tinytuya wizard` (gera `devices.json` com `id` e `key`) e `uv run python -m tinytuya scan` (mostra IP e versão), e digite os valores.

> A `local_key` muda se você parear a lâmpada de novo no app. Nesse caso, rode o setup outra vez.
> Reserve o IP da lâmpada no roteador (DHCP estático).

### Ar-condicionado (SmartThings)

#### Personal Access Token (atual)

1. Acesse <https://account.smartthings.com/tokens> e crie um token com as permissões de **Devices**: *List all devices*, *See all devices* e *Control all devices* (`r:devices:*`, `x:devices:*`).
2. Rode o setup, cole o token e escolha o ar-condicionado.

**Limitação:** PATs criados depois de 30/12/2024 valem só **24 horas**. Quando expirar, o app mostra "Token da SmartThings inválido ou expirado" e você roda o setup de novo.

#### OAuth com refresh token (para não renovar todo dia)

A autenticação fica isolada em `mothlit/devices/smartthings.py`. O `SmartThingsClient` só chama `auth.token()` e, se receber HTTP 401, tenta `auth.renovar()` uma vez. Para usar OAuth basta uma classe `AuthOAuth` com esses dois métodos, sem mexer no resto. *(Ainda não implementada: fica para uma próxima fase.)*

Passos para obter as credenciais:

1. Instale a [SmartThings CLI](https://github.com/SmartThingsCommunity/smartthings-cli). O tipo de app OAuth não aparece no Developer Workspace.
2. `smartthings apps:create` › escolha **OAuth-In App**. Informe um nome, os escopos `r:devices:*` e `x:devices:*` e uma *redirect URI* (ex.: `https://httpbin.org/get`). Guarde o **client_id** e o **client_secret**.
3. Abra no navegador:
   `https://api.smartthings.com/oauth/authorize?client_id=<ID>&response_type=code&redirect_uri=<URI>&scope=r:devices:*+x:devices:*`
   Autorize e copie o `code` da URL de retorno.
4. Troque o `code` por tokens fazendo um `POST` no endpoint de token com *Basic auth* `client_id:client_secret` e `grant_type=authorization_code&code=<code>&redirect_uri=<URI>`.
5. Para renovar, faça o mesmo `POST` com `grant_type=refresh_token&refresh_token=<atual>`.

Pontos importantes:

- O access token dura cerca de 24 h. O refresh token vale de 29 a 30 dias se não for usado.
- **Cada refresh token só pode ser usado uma vez.** A resposta traz um novo, que precisa ir para o keyring imediatamente. Se a cadeia quebrar, é preciso autorizar de novo (passo 3).
- A documentação oficial e a comunidade citam URLs diferentes para o endpoint de token (`https://api.smartthings.com/oauth/token` e `https://api.smartthings.com/v1/oauth/token`). Confirme a URL atual em [Token management](https://developer.smartthings.com/docs/service-integrations/token-management).

## Uso

```powershell
uv run python -m mothlit test-lampada   # liga, muda brilho/temperatura/cor e restaura o estado inicial
uv run python -m mothlit test-ar        # mostra capabilities e estado; comandos só se você confirmar
```

## Estrutura

```
mothlit/
  __main__.py            CLI (setup, test-lampada, test-ar)
  config.py              .env + keyring
  setup.py               onboarding interativo
  devices/
    base.py              protocolo Device + ErroDispositivo
    lampada.py           tinytuya.BulbDevice (detecta tipo e recursos pelos DPS)
    smartthings.py       cliente httpx + autenticação (AuthPAT)
    ar_condicionado.py   capabilities switch, thermostatCoolingSetpoint,
                         airConditionerMode, airConditionerFanMode, temperatureMeasurement
tests/                   pytest com mocks (tinytuya mockado, httpx.MockTransport)
```

## Detalhes técnicos

- **Lâmpada**: o tipo (A/B/C) é detectado pelos DPS com `detect_bulb()`. Temperatura de cor e cor só aparecem se a lâmpada tiver esses recursos. O tempo limite é de 2 s com 2 tentativas, em vez do padrão do tinytuya (5 s × 5 tentativas). O socket é protegido por uma trava, porque o tinytuya não é thread-safe.
- **Ar-condicionado**:
  - As capabilities vêm de `GET /devices/{id}`, descontando as listadas em `custom.disabledCapabilities`.
  - Os modos e as velocidades vêm de `availableAcModes` e `availableAcFanModes`, que mudam conforme o modo atual (em `auto`, por exemplo, só existe ventilador `auto`). Se elas não vierem, o app usa `supportedAcModes` e `supportedAcFanModes`.
  - A faixa de temperatura vem de `coolingSetpointRange`. Se não vier, o padrão é 16–30 °C.

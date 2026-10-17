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

O setup pergunta como o Mothlit vai acessar a SmartThings:

#### 1. OAuth (recomendado: autoriza uma vez e renova sozinho)

O access token dura cerca de 24 h e é **renovado automaticamente** com o refresh token, que vale 30 dias e muda a cada renovação. Enquanto o Mothlit rodar ao menos uma vez a cada 30 dias, você não precisa fazer mais nada (com "Iniciar com o Windows" ligado, isso é praticamente garantido).

Passo único, criar um app OAuth na sua conta com a [SmartThings CLI](https://github.com/SmartThingsCommunity/smartthings-cli) (o cadastro pelo site ainda não está disponível):

1. Instale a CLI: baixe e rode o `smartthings.msi` da [página de releases](https://github.com/SmartThingsCommunity/smartthings-cli/releases).
2. Rode `smartthings apps:create`. Na primeira vez, ele abre o navegador para você entrar na conta Samsung.
   - Tipo de app: **OAuth-In App**
   - Display Name: `Mothlit` · Description: qualquer texto · Icon Image URL e Target URL: em branco
   - Escopos: `r:devices:*` e `x:devices:*`
   - Redirect URI: **Add Redirect URI** › `https://httpbin.org/get` › *Finish editing Redirect URIs* › *Finish and create OAuth-In SmartApp*
3. Guarde o **OAuth Client Id** e o **OAuth Client Secret**. O secret só aparece uma vez.
4. Rode `uv run python -m mothlit setup`, escolha **OAuth** e cole o Client Id e o Client Secret. O navegador abre a tela de autorização da Samsung. Depois de autorizar, ele vai para uma página do httpbin: copie o **endereço completo** da barra do navegador e cole no setup.

Detalhes:
- As credenciais (client id/secret e tokens) ficam no keyring, em pedaços se forem grandes (o Windows limita cada segredo a ~1280 caracteres).
- Cada refresh token só pode ser usado uma vez. O Mothlit grava o novo no keyring na hora e renova de forma thread-safe (várias chamadas simultâneas causam uma única renovação).
- O Mothlit tenta `https://api.smartthings.com/oauth/token` e, se não existir, `.../v1/oauth/token` (a documentação nova e a comunidade citam endereços diferentes).
- Se a autorização expirar (mais de 30 dias sem rodar, ou revogada), o app avisa e basta rodar o setup de novo.

#### 2. Token pessoal (PAT)

1. Acesse <https://account.smartthings.com/tokens> e crie um token com as permissões de **Devices**: *List*, *See* e *Control* (`r:devices:*`, `x:devices:*`).
2. No setup, escolha **Token pessoal** e cole o token.

**Limitação:** PATs criados depois de 30/12/2024 valem só **24 horas**. Quando expirar, cole um novo em **Configurações › Acesso à SmartThings**: o Mothlit valida o token antes de salvar.
## Uso

```powershell
uv run python -m mothlit                # abre a interface
uv run python -m mothlit test-lampada   # liga, muda brilho/temperatura/cor e restaura o estado inicial
uv run python -m mothlit test-ar        # mostra capabilities e estado; comandos só se você confirmar
```

### Bandeja do sistema

- **–** (minimizar) esconde a janela na bandeja; **×** encerra o app (ou vai para a bandeja, veja abaixo).
- Clique no ícone da mariposa para reabrir. O menu tem **Ligar/Desligar luz**, **Ligar/Desligar ar** (o texto acompanha o estado atual) e **Sair**. Ações pela bandeja mostram uma notificação do Windows.
- O estado dos dois aparelhos é relido a cada 30 s (e no botão ⟳ ou F5).
- Só existe uma instância: abrir o Mothlit de novo traz a janela que já está rodando (inclusive se ele iniciou escondido).

### Configurações (botão de ajustes)

- **Iniciar com o Windows**: grava `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` (só o seu usuário, sem admin). O Mothlit abre escondido na bandeja (`--bandeja`), sem console.
- **Minimizar na bandeja ao fechar**: o × e o Alt+F4 escondem o app; para encerrar, use **Sair** no menu da bandeja. Fica salvo em `%APPDATA%\Mothlit\preferencias.json`.
## Executável (Windows)

```powershell
uv run pyinstaller empacotamento/mothlit.spec --noconfirm        # gera dist\Mothlit\
powershell -ExecutionPolicy Bypass -File empacotamento\instalar.ps1
```

Ou dê dois cliques em `empacotamento\instalar.cmd`: ele roda o instalador e espera um Enter no final para você ler o resultado (ou o erro).

O build gera uma pasta (`onedir`) com dois executáveis que compartilham as dependências:

| Arquivo | Para quê |
|---|---|
| `Mothlit.exe` | Interface e bandeja, sem console. É ele que inicia com o Windows. |
| `mothlit-cli.exe` | Linha de comando: `mothlit-cli setup`, `test-lampada`, `test-ar`. |

Usei pasta em vez de arquivo único porque o `onefile` se descompacta numa pasta temporária a cada abertura: inicia mais devagar (ruim para "Iniciar com o Windows") e costuma gerar falso positivo de antivírus.

O `instalar.ps1` (sem administrador):
- copia para `%LOCALAPPDATA%\Programs\Mothlit` e cria o atalho **Mothlit** no Menu Iniciar;
- fecha o Mothlit instalado se ele estiver aberto;
- se "Iniciar com o Windows" estiver ligado, aponta o registro para o novo `Mothlit.exe`.

Configuração (`%APPDATA%\Mothlit`) e segredos (keyring) ficam fora da pasta do app, então reinstalar ou atualizar não perde nada. **Para atualizar** o app instalado depois de mudanças no código, dê dois cliques em `empacotamento\atualizar.cmd`: ele gera o build, roda `mothlit-cli verificar` no executável novo (ícones, interface, bandeja, keyring; sem abrir janela nem usar a rede) e só reinstala se tudo passar. O app instalado é uma cópia e não muda sozinho. Se o Mothlit estiver aberto, o instalador pede para ele sair (sem deixar ícone fantasma na bandeja) e o reabre na bandeja com a versão nova.

O executável grava um log em `%APPDATA%\Mothlit\mothlit.log` (com rotação, até ~3 MB): é onde olhar se algo der errado, já que não há console.

Requisito: WebView2 Runtime, que já vem no Windows 11.
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
                         airConditionerMode, airConditionerFanMode, temperatureMeasurement,
                         fanOscillationMode, custom.airConditionerOptionalMode
  tray.py                ícone na bandeja (pystray) com ações rápidas
  inicializacao.py       iniciar com o Windows (registro Run do usuário)
  ui/
    app.py               janela pywebview (sem moldura) + Api: a ponte que o JavaScript chama
    marca.py             gera o .ico da mariposa a partir de web/moth.svg
    web/                 interface em HTML/CSS/JS (index.html, estilo.css, app.js, moth.svg)
empacotamento/            mothlit.spec (PyInstaller), mothlit_app.py (entrada do .exe), instalar.ps1/.cmd, atualizar.cmd
tests/                   pytest com mocks (tinytuya mockado, httpx.MockTransport)
```

## Detalhes técnicos

- **Interface**: [pywebview](https://pywebview.flowrl.com/) usando o WebView2 (motor do Edge, já incluso no Windows 11). O visual é HTML/CSS/SVG, com transições aceleradas por GPU. Cada chamada do JavaScript para `pywebview.api` roda numa thread separada no Python, então a rede nunca trava a interface. Para abrir as ferramentas de desenvolvedor: `set MOTHLIT_DEBUG=1`.
- **Lâmpada**: o tipo (A/B/C) é detectado pelos DPS com `detect_bulb()`. Temperatura de cor e cor só aparecem se a lâmpada tiver esses recursos. O tempo limite é de 2 s com 2 tentativas, em vez do padrão do tinytuya (5 s × 5 tentativas). O socket é protegido por uma trava, porque o tinytuya não é thread-safe.
- **Ar-condicionado**:
  - As capabilities vêm de `GET /devices/{id}`, descontando as listadas em `custom.disabledCapabilities`.
  - Os modos e as velocidades vêm de `availableAcModes` e `availableAcFanModes`, que mudam conforme o modo atual (em `auto`, por exemplo, só existe ventilador `auto`). Se elas não vierem, o app usa `supportedAcModes` e `supportedAcFanModes`.
  - A faixa de temperatura vem de `coolingSetpointRange`. Se não vier, o padrão é 16–30 °C.

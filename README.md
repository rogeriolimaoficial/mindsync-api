# ROGVIL MindSync

Recolhe sinais de comportamento no PC e, com labels de energia, treina um modelo de estado cognitivo. Biometria só do sono (previsão do pico). O comportamento no PC ajusta essa previsão durante o dia.

## Ficheiros
| Ficheiro | Função |
|---|---|
| `tracker.py` | corre no PC do utilizador, envia janelas de 5s |
| `main.py` | servidor FastAPI (ingestão, wearables, labels, dashboard, downloads) |
| `features.py` | agrega janelas de 5s em blocos de 15 min |
| `view_data.py` | imprime os blocos de um utilizador/dia |
| `auth.py`, `server.py`, `get_token.py`, `get_sleep_data.py` | autorização e leitura de sono da Oura |

## Correr
```
pip install -r requirements.txt            # servidor
pip install -r requirements-tracker.txt    # tracker
export MINDSYNC_API_TOKEN=...              # token do servidor
uvicorn main:app --port 8000
```
Tracker: copia `config.example.txt` para `config.txt`, preenche `USER_ID` e `API_TOKEN` (o mesmo do servidor) e corre `python tracker.py`.

## Dados
**Tracker (janela de 5s, só janelas ativas, totais e não médias):** teclas, backspaces, episódios de correção (backspaces com menos de 1s entre si contam como 1), intervalos entre teclas (n, soma, soma dos quadrados), micro-pausas (2 a 10s), distância percorrida, deslocamento em linha reta, tempo de gesto, mudanças de direção, cliques. Nunca se guarda o que se escreve. Timestamps das teclas ficam 7 dias em `raw/` (local, ignorado pelo git).

**Servidor:** guarda as janelas em `windows_5s` (sem duplicados). Os blocos de 15 min são calculados em `features.py` somando os totais e dividindo no fim.

**Features por bloco:** `typing_kpm`, `backspace_ratio_pct`, `corr_eps_per_min`, `pauses_per_min`, `iki_mean_ms`, `iki_std_ms`, `mouse_speed_px_s`, `straightness_pct`, `dir_changes_per_1000px`, `active_pct`. `reliable=0` quando há menos de 2 min de escrita ativa.

## Plano
1. Uso próprio durante 1 semana: a curva do dia é estável de dia para dia?
2. Check-in de energia (1 a 5) a cada 60 a 90 min, via `/api/labels`.
3. 2 a 4 semanas com os dois: os sinais acompanham a energia reportada, dentro de cada pessoa?
4. Se sim, treinar o modelo base. Se não, rever as features.

## Segurança
Nunca commitar `.env`, `token.json`, `config.txt` nem `*.db` (estão no `.gitignore`).

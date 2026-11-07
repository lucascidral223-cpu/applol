"""
Coletor de estatisticas do LoL (API oficial da Riot) -> gera data.json

Uso:
  1) Pegue uma chave em https://developer.riotgames.com
  2) export RIOT_KEY="RGAPI-..."        (Windows: set RIOT_KEY=RGAPI-...)
  3) python coletor.py 5000             (numero de partidas a coletar)

Pode rodar varias vezes: ele continua de onde parou e soma as partidas novas.
Coloque o data.json na mesma pasta do meu-lol.html.
"""
import os, sys, json, time, urllib.request, urllib.error

KEY = (os.environ.get("RIOT_KEY") or "").strip().strip('"').strip("'")
if not KEY:
    sys.exit("Defina a variavel RIOT_KEY.")
print(f"Chave lida: {len(KEY)} caracteres, comeca com RGAPI-: {KEY.startswith('RGAPI-')} (o normal sao 42 caracteres)")
PLAT, REG = "br1", "americas"          # servidor BR
TIERS, DIVS, PAGES = ["EMERALD", "DIAMOND"], ["I", "II", "III", "IV"], 2
PER_PLAYER = 10                         # partidas recentes por jogador
MAX_MATCHES = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
PAUSE = 1.25                            # chave de desenvolvedor: 100 req / 2 min
OUT = "data.json"


def get(url, headers=None):
    while True:
        req = urllib.request.Request(url, headers={"X-Riot-Token": KEY, "User-Agent": "meu-lol/1.0"} if headers is None else headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                time.sleep(PAUSE if headers is None else 0)
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(int(e.headers.get("Retry-After", "10")) + 1)
                continue
            if e.code in (401, 403):
                sys.exit(f"Erro {e.code} da Riot em {url.split('?')[0]}. Chave invalida ou expirada: gere outra no portal da Riot e atualize o segredo RIOT_KEY.")
            return None
        except Exception:
            time.sleep(5)


DD = "https://ddragon.leagueoflegends.com"
version = get(DD + "/api/versions.json", headers={})[0]
items = get(f"{DD}/cdn/{version}/data/pt_BR/item.json", headers={})["data"]
FINAL = {i for i, it in items.items()
         if it["gold"]["purchasable"] and it["maps"].get("11") and not it.get("into") and it["gold"]["total"] >= 900}

data = {"agg": {}, "seen": []}
if os.path.exists(OUT):
    data = json.load(open(OUT, encoding="utf-8"))
data["version"] = version
agg, seen = data["agg"], set(data["seen"])


def save():
    data["seen"] = list(seen)
    json.dump(data, open(OUT, "w", encoding="utf-8"))


def process(m):
    info = m["info"]
    if info["queueId"] != 420 or info["gameDuration"] < 900:
        return False
    by = {(p["teamPosition"], p["teamId"]): p for p in info["participants"] if p["teamPosition"]}
    for (role, team), p in by.items():
        a = agg.setdefault(p["championName"], {}).setdefault(role, {"g": 0, "w": 0, "i": {}, "o": {}})
        a["g"] += 1
        a["w"] += int(p["win"])
        for k in range(6):
            iid = str(p[f"item{k}"])
            if iid in FINAL:
                a["i"][iid] = a["i"].get(iid, 0) + 1
        opp = by.get((role, 300 - team))
        if opp:
            # o = [jogos, vitorias, itens, dif_cs, dif_abates_solo, dif_nivel, jogos_com_detalhe]
            o = a["o"].setdefault(opp["championName"], [0, 0, {}, 0, 0, 0, 0])
            if len(o) < 7:  # dados antigos so tinham [jogos, vitorias]
                o += [{}, 0, 0, 0, 0]
            o[0] += 1
            o[1] += int(p["win"])
            ch, oc = p.get("challenges") or {}, opp.get("challenges") or {}
            dif = lambda k: (ch.get(k) or 0) - (oc.get(k) or 0)
            o[3] += dif("maxCsAdvantageOnLaneOpponent")
            o[4] += dif("soloKills")
            o[5] += dif("maxLevelLeadLaneOpponent")
            o[6] += 1
            for k in range(6):
                iid = str(p[f"item{k}"])
                if iid in FINAL:
                    o[2][iid] = o[2].get(iid, 0) + 1
    return True


def players():
    for t in TIERS:
        for d in DIVS:
            for pg in range(1, PAGES + 1):
                es = get(f"https://{PLAT}.api.riotgames.com/lol/league/v4/entries/RANKED_SOLO_5x5/{t}/{d}?page={pg}") or []
                for e in es:
                    if e.get("puuid"):
                        yield e["puuid"]


n = 0
try:
    for puuid in players():
        ids = get(f"https://{REG}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?queue=420&type=ranked&count={PER_PLAYER}") or []
        for mid in ids:
            if mid in seen:
                continue
            m = get(f"https://{REG}.api.riotgames.com/lol/match/v5/matches/{mid}")
            seen.add(mid)
            if m and process(m):
                n += 1
                if n % 50 == 0:
                    save()
                    print(f"{n} partidas coletadas")
            if n >= MAX_MATCHES:
                raise StopIteration
except (StopIteration, KeyboardInterrupt):
    pass
finally:
    save()
    print(f"Pronto: {n} partidas novas. Arquivo: {OUT}")

# software-factory

O fabrică de software pentru Claude Code. Îi dai o cerere, iar agenții o analizează, scriu specificația, construiesc, verifică printr-un script, fac review și deschid o cerere de unire (PR). Unirea finală o faci tu.

Repo-ul e public și **nu are site**. Nimic de aici nu se publică: fabrica nu are nicio comandă de deploy.

## Cum o folosești

1. Deschide Claude Code în folderul `software-factory`.
2. Scrie `/factory adaugă un instrument care ...`. Se creează un issue cu eticheta `factory` și pornește lucrarea.
3. Când lucrarea e gata, primești linkul PR-ului și explicația în română. Dacă totul e bine, apeși **Merge** pe GitHub.

Alte comenzi:

| Comandă | Ce face |
|---|---|
| `/factory run` | ia toate issue-urile cu eticheta `factory` și reia ce a rămas neterminat |
| `/factory issue 12` | lucrează doar issue-ul 12 |
| `/factory rework 12` | trimite lucrarea înapoi, cu comentariile tale de pe PR |

Panoul vizual: `cd factory && python -m http.server`, apoi deschide http://localhost:8000/dashboard.html.

## Ce oprește o greșeală

- **`factory/checks.sh`** rulează testele înainte de orice review. Agenții nu îl pot modifica.
- **`factory/bin/gate`** respinge orice lucrare care atinge `.github/`, configurații de hosting sau fișierele fabricii.
- **`factory/bin/guard`** blochează comenzile care ar publica ceva sau ar atinge alt proiect.
- **`auto_merge` e oprit** în `factory/config.json`, deci nimic nu se unește fără tine.
- **`repo`** din `factory/config.json`: fabrica refuză să ruleze dacă nu e în acest repo.

Limită: garda prinde greșeli, nu rea-voință, iar agenții folosesc contul tău GitHub. Pentru o barieră tare, vezi [mai jos](#token-limitat).

## Token limitat

Un token care vede doar acest repo oprește comenzile `gh` și `git push` date din acest folder să atingă alt proiect de pe GitHub. Nu acoperă comenzile date din alt folder, pe care le oprește doar garda:

1. Pe GitHub: **Settings → Developer settings → Fine-grained tokens → Generate new token**.
2. La **Repository access** alege doar `Ramanul/software-factory`.
3. La **Permissions** dă Read and write la **Contents**, **Issues** și **Pull requests**.
4. Copiază tokenul în `.claude/settings.local.json`, fișier pe care git îl ignoră:

```json
{ "env": { "GH_TOKEN": "tokenul-tău" } }
```

Tokenul se introduce manual. Nu-l da niciunui agent în chat.

## Originea și licența

Bazată pe [Software Factory for Claude Code v2](https://github.com/zazencodes/zazencodes-season-3/tree/main/src/software-factory-claude-code-v2) de ZazenCodes, sub licența GPL-3.0, la fel ca acest repo.

Diferențe față de original:

- Instrucțiunile și agenții nu sunt publicați acolo, așa că au fost refăcuți din versiunea 1 și din `BUILD_PROMPT.md` și `DESIGN.md`.
- Scripturile sunt reparate pentru Windows.
- Sunt adăugate `factory/bin/guard`, `factory/bin/argon`, `blocked_paths`, `auto_merge` și verificarea `repo`.
- Intake rulează pe Opus în loc de Fable.

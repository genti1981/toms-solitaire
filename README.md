# Tom's Solitaire

Lojë solitaire (Klondike) e shkruar në Python me `tkinter`, pa varësi të
jashtme. Dizajni i kësaj loje i kushtohet kolegut tonë **Ing. Tomorr Spahiu**,
në shenjë respekti për punën e tij.

## Si të luash

1. Instalo **Python 3** (me `tkinter` — në Windows dhe macOS vjen bashkë me
   Python; në Linux mund të duhet paketa `python3-tk`).
2. Shkarko lojën: butoni jeshil **Code → Download ZIP**, ose merr skedarin
   `solitaire.py` bashkë me dosjen `cards/`.
3. Nga dosja e lojës hape terminalin dhe shkruaj:

   ```
   python3 solitaire.py
   ```

Mbaje gjithmonë dosjen `cards/` **pranë** `solitaire.py` — aty janë figurat e
letrave dhe letra e pasme.

## Çfarë ka brenda

- `solitaire.py` — vetë loja
- `cards/` — figurat e letrave (asët, fantët/damat/mbretërit dhe letra e pasme)
- `version.json` — të dhënat e versionit, për përditësimet automatike
- `README.md` — ky skedar

## Rezultatet online (tabela e rezultateve)

Rezultatet mund të ndahen mes disa lojtarëve përmes një *gist* në GitHub.
Konfigurohet lart te `solitaire.py`:

- `LEADERBOARD_GIST_ID` — id e një gist që përmban skedarin `scores.json` me
  përmbajtje fillestare `[]`
- `LEADERBOARD_TOKEN` — token GitHub me të drejtën **gist** (nevojitet vetëm
  për të *shkruar* rezultate; leximi bëhet edhe pa të)

Të gjithë lojtarët përdorin të njëjtin `LEADERBOARD_GIST_ID` dhe `LEADERBOARD_TOKEN`.

## Përditësimet automatike

Loja lexon `version.json` nga kjo depo. Kur fusha `version` aty është më e lartë
se `VERSION` brenda `solitaire.py`, loja ofron të shkarkojë skedarët e listuar te
`files`. Konfigurohet lart te `solitaire.py`:

- `UPDATE_REPO` — emri i depozitës, p.sh. `"genti1981/toms-solitaire"`
- `UPDATE_BRANCH` — zakonisht `"main"`

Lëre `UPDATE_REPO` bosh nëse nuk do përditësime automatike.

### Si të publikosh një version të ri

1. Rrit `VERSION` brenda `solitaire.py` (p.sh. nga `1.0.0` në `1.1.0`) dhe
   ngarko këtë skedar të ri në depo (dhe çdo aset të ndryshuar te `cards/`).
2. Përditëso `version.json`:
   - vër **të njëjtin** numër te `version` (p.sh. `1.1.0`);
   - shkruaj te `notes` çfarë ndryshoi — ky tekst u shfaqet lojtarëve;
   - te `files` listo skedarët për t'u shkarkuar (zakonisht vetëm
     `solitaire.py`; shto p.sh. `cards/back.png` kur ndryshon ndonjë figurë).
3. Herën tjetër që kolegët hapin lojën, marrin njoftimin dhe mund të
   përditësohen me një klik.

**Shënim:** GitHub i ruan përkohësisht (*cache*) skedarët `raw` për disa minuta,
prandaj shpërndarja e një versioni të ri mund të vonojë pak.

## Format i `version.json`

```json
{
  "version": "1.0.0",
  "notes": "Përshkrimi i ndryshimeve.",
  "files": ["solitaire.py"]
}
```

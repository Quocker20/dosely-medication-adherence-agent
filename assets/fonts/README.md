# Fonts

`NotoSans-Regular.ttf` / `NotoSans-Bold.ttf` — static-weight instances (wght=400/700, wdth=100)
extracted from Google's `NotoSans[wdth,wght].ttf` variable font via `fontTools.varLib.instancer`
(fonttools ships as an `fpdf2` dependency). Source:
https://github.com/google/fonts/blob/main/ofl/notosans/NotoSans%5Bwdth,wght%5D.ttf

Used by `src/modules/prescriptions/pdf.py` to render Vietnamese diacritics — fpdf2's built-in core
fonts are Latin-1 only. See `docs/prescription-pdf-export-plan.md` §6 Step 1.

Licensed under the SIL Open Font License 1.1 — see `OFL.txt`.
